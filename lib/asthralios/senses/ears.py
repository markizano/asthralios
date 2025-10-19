import os
import random
import pasimple
import numpy as np
import multiprocessing as mp
import urllib3, urllib
import re
import time
import traceback as tb
from typing import Generator, NamedTuple

import torch
from TTS.api import TTS

from faster_whisper import WhisperModel
from faster_whisper.vad import VadOptions, get_vad_model

import kizano
log = kizano.getLogger(__name__)

import asthralios.gpt as gpt

WHISPER_MODEL = os.environ.get('WHISPER_MODEL', 'guillaumekln/faster-whisper-large-v2')
TTS_MODEL = os.environ.get('TTS_MODEL', 'tts_models/multilingual/multi-dataset/xtts_v2')
TTS_TYPE = os.environ.get('TTS_TYPE', 'local').lower()
TTS_ADAPTER = os.environ.get('ADAPTER', 'api').lower()
LANGUAGE = os.environ.get('LANGUAGE', 'en')

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
            speech_pad_ms=350,
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
        if self.pool.input.process.is_alive():
            self.pool.input.process.terminate()
            if self.pool.input.process._Popen is not None:
                self.pool.input.process.join()

        if self.pool.output.process.is_alive():
            self.pool.output.process.terminate()
            if self.pool.output.process._Popen is not None:
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
                rate=self.config.get('input_sample_rate', PulseClient.SAMPLE_SIZE),
                app_name='asthralios',
                stream_name='asthralios-ears')
        return self._istream

    def getPulseOutput(self) -> pasimple.PaSimple:
        if not self._ostream:
            self._ostream = pasimple.PaSimple(pasimple.PA_STREAM_PLAYBACK,
                format=pasimple.PA_SAMPLE_S16LE,
                channels=1,
                rate=self.config.get('output_sample_rate', 48000),
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
        log.info(f'Heard {silence} seconds of post-speech silence. Collected {len(result)} samples.')
        return result

    def speak(self, audio: np.ndarray):
        '''
        Speak the audio to the output stream.
        Buffer/stream the audio if it is too long.
        '''
        # if len(audio) > self.SAMPLE_SIZE * 3:
        #     for i in range(0, len(audio), self.SAMPLE_SIZE):
        #         self.pool.output.queue.put(audio[i:i+self.SAMPLE_SIZE])
        # else:
        self.pool.output.queue.put(audio)

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

class Conversation(object):
    '''
    Converse with the user:
    - Open a connection to the audio both as input and output (mic and speakers for voice and ears).
    - Listen to the user's voice and convert it to text.
    - Respond to the user's voice with text.
    - Convert the text to speech and play it back to the user.
    Do so in a thread-like manner to ensure the main thread is always responsive and we seem like a live
    conversation (this should tolerate interruptions).
    '''

    def __init__(self, config: dict):
        self.config = config
        log.info('Connecting to ears and voicebox...')
        self.pulse = PulseClient(config)
        log.info('Loading language-interpreter model...')
        self.model = WhisperModel(
            config.get('whisper.model', WHISPER_MODEL),
            device=config.get('whisper.device', 'cuda'),
            compute_type=config.get('whisper.compute_type', 'auto'),
            cpu_threads=os.cpu_count(),
        )
        log.info('Loading vocal chords...')
        if self.isTTSLocal():
            if TTS_ADAPTER == 'api':
                device = "cuda" if torch.cuda.is_available() else "cpu"
                tts_model_name = config.get('tts', {}).get('model', TTS_MODEL)
                self.tts = TTS(tts_model_name).to(device=torch.device(device))
            elif TTS_ADAPTER == 'model':
                self.loadXTTSModel()

        self.gpt = gpt.LocalGPT(host='chatgpt')
        self.listening = True

    @property
    def listening(self) -> bool:
        return self.pulse.listening

    @listening.setter
    def listening(self, value: bool):
        self.pulse.listening = value

    def isTTSLocal(self) -> bool:
        return TTS_TYPE == 'local'

    def loadXTTSModel(self):
        '''
        Directly load the TTSv2 model.
        '''
        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import Xtts
        self.xtts_config = XttsConfig()
        home = os.environ.get('HOME', '/home/stable-diffusion')
        self.xtts_config.load_json(f"{home}/.local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2/config.json")
        self.tts = Xtts.init_from_config(self.xtts_config)
        self.tts.load_checkpoint(self.xtts_config, checkpoint_dir=f"{home}/.local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2/", eval=True)
        # if torch.cuda.is_available():
        #     self.tts.cuda()

    def voiceToText(self, audio: np.ndarray) -> str:
        '''
        Convert the audio received to text quickly.
        '''
        log.info('Voice 2 Text')
        segments, info = self.model.transcribe(
            audio,
            language=LANGUAGE,
            without_timestamps=True,
            word_timestamps=False,
            vad_filter=True,
            vad_parameters=self.pulse.vad_options
        )
        log.debug(info)
        return ' '.join([ segment.text for segment in segments ])


    def listen(self) -> Generator[str, None, None]:
        '''
        Listen into perpetuity for queries from the end-user.
        Always have your ears open.
        '''
        if not self.listening: self.listening = True
        for audio in self.pulse.listen():
            yield self.voiceToText(audio)

    def textToVoice(self, text: str, q: mp.Queue) -> int:
        '''
        Generate speech from text.
        '''
        log.info(f'Text to voice: {text}')
        if self.isTTSLocal():
            if TTS_ADAPTER == 'api':
                wav = self.tts.tts(text, speed=1.0, split_sentences=True)
            elif TTS_ADAPTER == 'model':
                home = os.environ.get('HOME', '/home/stable-diffusion')
                speaker_wav = f'{home}/.local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2/speaker.wav'
                wav = self.tts.synthesize(text, config=self.xtts_config, speaker_wav=speaker_wav, language=LANGUAGE)
            npwav = np.array(wav, dtype=np.float32)
            audio = np.array(npwav * (32768 / max(0.01, np.max(np.abs(npwav)))), dtype=np.int16)
            q.put(audio)
        else:
            request = urllib3.PoolManager()
            TTS_API = os.environ.get('TTS_API', None)
            if TTS_API == 'tts':
                params = {
                    'text': text,
                    'language': LANGUAGE,
                    # 'speaker_id': 'Dionisio Schuyler', # Nice deep voice.
                    'speaker_id': 'Filip Traverse', # cute irish accent
                }
                response = request.request('GET', 'http://tts/api/tts', fields=params)
            elif TTS_API == 'kizano':
                # urltext = urllib.parse.quote(text)
                response = request.request('GET', f'http://tts/{text}')
                return 0 # Return early here because if you are using my API, I will play it from that server.
            audio = np.frombuffer(response.data, dtype=np.int16)
            q.put( audio )
        return 0

    def speak(self, text: str):
        '''
        Speak the text to the user.
        '''
        paragraphs = text.split('\n\n')
        log.info(f'Speak paragraphs: {paragraphs}')
        pool: list[ProcessQueue] = []
        for paragraph in paragraphs:
            q = mp.Queue()
            pq = mp.Process(target=self.textToVoice, args=(paragraph, q))
            pool.append(ProcessQueue(pq, q))
            pq.start()
        log.info(f'started generation of voice clips ({len(pool)})...')

        for i, pq in enumerate(pool):
            audio = pq.queue.get()
            log.info(f'Vocalize: {paragraphs[i]}')
            self.pulse.speak(audio)

        for pq in pool:
            pq.process.join()
        log.info('Voice clips generated and spoken.')
        return audio

    def converse(self, text: str):
        '''
        Have a conversation with the user.
        '''
        return self.gpt.chatExchange(text)

    def stop(self):
        '''
        Stop listening for conversation mode.
        '''
        self.listening = False
        return self.pulse.stop()

def conversate(config: dict) -> int:
    chat = Conversation(config)
    chat.speak('Hello, I am Asthralios. How may I help you?')
    while chat.listening:
        log.info('Asthralios is listening...')
        time.sleep(1)
        try:
            for query in chat.listen():
                log.info(f"\x1b[34mRead\x1b[0m: {query}")
                if query:
                    response = chat.converse(query)
                    log.info(f"last message: {response}")
                    # Manually tracked requests that I can intercept herre in code.
                    if re.match(r'pause.*60.*sec(?:ond)?s?', response.lower().strip()):
                        log.info('You asked me to wait a minute...')
                        time.sleep(60)
                        continue
                    if re.match(r'goodbye|end\s+program', response.lower().strip()):
                        log.info('Exiting interactive mode...')
                        chat.listening = False
                        chat.speak('goodbye and good night')
                        break
                    chat.speak(response)
        except KeyboardInterrupt:
            log.error('Ctrl+C detected... closing my ears ...')
            chat.listening = False
        except RuntimeWarning as rw:
            log.error(f"Model failed: {rw}")
            log.error('Fatal.')
            chat.listening = False
        except Exception as e:
            log.error(f"Sorry, I missed that: {e}")
            log.error(tb.format_exc())
    log.info('Exiting interactive mode.')
    return 0
