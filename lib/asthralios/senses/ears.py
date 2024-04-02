import io, os
import random
import pasimple
import numpy as np
import multiprocessing as mp
from typing import Generator, NamedTuple

import torch
from TTS.api import TTS

from faster_whisper import WhisperModel, format_timestamp
from faster_whisper.vad import VadOptions, get_vad_model

import kizano
log = kizano.getLogger(__name__)

import asthralios.gpt as gpt

class ProcessQueue(NamedTuple):
    '''
    A named tuple to store the mp.Process and mp.Queue
    '''
    process: mp.Process
    queue: mp.Queue

class PulseIO(NamedTuple):
    '''
    A named tuple to store the Process and Queue for the PulseAudio client.
    '''
    input: ProcessQueue
    output: ProcessQueue

class PulseClient(object):
    '''
    This client acts like both a buffer to the PulseAudio streams and a controller internally
    for listening or speaking on the streams.
    This takes the heavy burden off of the main thread and allows for a more responsive interface.
    '''
    SAMPLE_SIZE = 16000

    def __init__(self, config: kizano.Config):
        self.config = config
        self.vad_options = VadOptions(
            threshold=0.1,
            min_speech_duration_ms=450,
            max_speech_duration_s=float("inf"),
            min_silence_duration_ms=200,
            window_size_samples=1024,
            speech_pad_ms=250,
        )
        iq = mp.Queue()
        oq = mp.Queue()
        self.pool: PulseIO = PulseIO(
            ProcessQueue(mp.Process(target=self.streamWords, args=(iq,)), iq),
            ProcessQueue(mp.Process(target=self.streamSpeech, args=(oq,)), oq)
        )
        self._istream: pasimple.PaSimple = None
        self._ostream: pasimple.PaSimple = None
        self._listening: bool = False

    def __del__(self):
        '''
        Clean up the pool of processes.
        '''
        self.pool.input.process.terminate()
        self.pool.input.process.join()

        self.pool.output.process.terminate()
        self.pool.output.process.join()

    @property
    def listening(self) -> bool:
        '''
        listening property
        '''
        return self._listening

    @listening.setter
    def listening(self, value: bool):
        '''
        listening setter
        '''
        self._listening = value
        if value:
            if self.pool.input.process._popen is None:
                self.pool.input.process.start()
            if self.pool.output.process._popen is None:
                self.pool.output.process.start()

    def _next_chunk(self, stream: pasimple.PaSimple) -> np.ndarray:
        '''
        Read the next chunk of audio from the stream.
        '''
        audio = np.frombuffer(
            stream.read(PulseClient.SAMPLE_SIZE * pasimple.format2width(stream.format())),
            dtype=np.int16
        ).astype(np.float32) / 32768.0
        return audio[~np.isnan(audio) & ~np.isinf(audio)]

    def getPulseInput(self) -> pasimple.PaSimple:
        if not self._istream:
            self._istream = pasimple.PaSimple(pasimple.PA_STREAM_RECORD,
                format=pasimple.PA_SAMPLE_S16LE,
                channels=1,
                rate=PulseClient.SAMPLE_SIZE,
                app_name='asthralios',
                stream_name='asthralios-ears')
        return self._istream

    def getPulseOutput(self) -> pasimple.PaSimple:
        if not self._ostream:
            self._ostream = pasimple.PaSimple(pasimple.PA_STREAM_PLAYBACK,
                format=pasimple.PA_SAMPLE_S16LE,
                channels=1,
                rate=48000,
                app_name='asthralios',
                stream_name='asthralios-voice')
        return self._ostream

    def getSoundOfWords(self, stream: pasimple.PaSimple, doneListening: int = 2) -> np.ndarray:
        '''
        Listen to the stream until silence is detected for 2s.
        Yield audio chunks as long as there is speech.
        @param doneListening: The number of seconds of silence to wait before stopping.
        '''
        result = np.array([]).astype(np.float32)
        audio = self._next_chunk(stream)
        silence = 0 # number of seconds we hear relative "silence" or speech below threshold
        has_spoken = False
        vad = get_vad_model()
        vad_state = vad.get_initial_state(batch_size=1)
        while silence < doneListening:
            speech_prob, vad_state = vad(audio, vad_state, stream.rate())
            if speech_prob > self.vad_options.threshold:
                silence = 0
                has_spoken = True
                log.info([random.choice(tuple(['uh-huh...', 'I hear you ...', 'yeap...', 'mm-hmm...', 'yes...', 'I am listening...']))])
                result = np.concatenate((result, audio), dtype=np.float32)
            else:
                if has_spoken:
                    silence += 1
                else:
                    log.debug("(I haven't heard you yet...).")
            audio = self._next_chunk(stream)
        log.info(f'Heard {silence} seconds of post-speech silence.')
        return result

    def speak(self, audio: np.ndarray):
        '''
        Speak the audio to the output stream.
        '''
        return self.pool.output.queue.put(audio)

    def listen(self) -> Generator[np.ndarray, None, None]:
        '''
        @async -- This function starts PID's to listen, but does not join them until the program exits.
        Run self.doListen() in a subprocess and receive chunks via a queue to ensure we are always pulling the latest
        audio from the stream and storing it in a local buffer.
        '''
        while self.listening:
            audio = self.pool.input.queue.get()
            yield audio
        return False

    def streamWords(self, q: mp.Queue) -> int:
        '''
        Stream audio from the mic to a queue.
        '''
        try:
            stream = self.getPulseInput()
        except pasimple.PaSimpleError as e:
            log.error(f"Error creating input: {e}")
            import pdb
            pdb.set_trace()
            return 1
        while self.listening:
            audio = self.getSoundOfWords(stream, 2)
            q.put(audio)
        return 0

    def streamSpeech(self, q: mp.Queue) -> int:
        '''
        @async
        Stream audio from the mic to a queue.
        '''
        try:
            stream = self.getPulseOutput()
        except pasimple.PaSimpleError as e:
            log.error(f"Error creating output: {e}")
            return 1
        
        audio: np.ndarray = q.get()
        while audio is not None:
            stream.write(audio.tobytes())
            audio = q.get()
        return 0

    def stop(self):
        '''
        Stop listening to the stream.
        '''
        self.listening = False

class LanguageCenter(object):
    '''
    Converts heard audio into something we can manage as text to interpret.
    '''
    def __init__(self, config: dict):
        self.config = config
        log.info('Connecting to ears and voicebox...')
        self.client = PulseClient(config)
        log.info('Loading language-interpreter model...')
        self.model = WhisperModel(
            config.get('whisper.model', os.getenv('WHISPER_MODEL', 'guillaumekln/faster-whisper-large-v2')),
            device=config.get('whisper.device', 'cuda'),
            compute_type=config.get('whisper.compute_type', 'auto'),
            cpu_threads=os.cpu_count(),
        )
        log.info('Loading vocal chords...')
        device = "cuda" if torch.cuda.is_available() else "cpu"
        tts_model_name = os.environ.get('TTS_MODEL', 'tts_models/en/jenny/jenny')
        self.tts = TTS(tts_model_name).to(device)
        self.gpt = gpt.LocalGPT(host='secretum.home.asthralios.net')
        self.listening = True

    @property
    def listening(self) -> bool:
        return self.client.listening

    @listening.setter
    def listening(self, value: bool):
        self.client.listening = value

    def toText(self, audio: np.ndarray) -> str:
        '''
        Convert the audio received to text quickly.
        '''
        segments, info = self.model.transcribe(
            audio,
            language=self.config.get('language', 'en'),
            without_timestamps=True,
            word_timestamps=False,
            vad_filter=True,
            vad_parameters=self.client.vad_options
        )
        log.debug(info)
        return ' '.join([ segment.text for segment in segments ])


    def listen(self) -> Generator[str, None, None]:
        '''
        Listen into perpetuity for queries from the end-user.
        Always have your ears open.
        '''
        if not self.listening: self.listening = True
        for audio in self.client.listen():
            yield self.toText(audio)

    def speak(self, text: str):
        '''
        Speak the text to the user.
        '''
        paragraphs = text.split('\n\n')
        for paragraph in paragraphs:
            wav = self.tts.tts(paragraph, speed=1.0, split_sentences=True)
            npwav = np.array(wav, dtype=np.float32)
            audio = np.array(npwav * (32768 / max(0.01, np.max(np.abs(npwav)))), dtype=np.int16)
            self.client.speak(audio)

        return audio

    def converse(self, text: str):
        '''
        Have a conversation with the user.
        '''
        return self.gpt.converse(text)
