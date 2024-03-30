import io, os
import random
import pasimple
import numpy as np
import multiprocessing as mp
from typing import Generator

from faster_whisper import WhisperModel, format_timestamp
from faster_whisper.vad import VadOptions, get_vad_model

import kizano
log = kizano.getLogger(__name__)

class PulseClient(object):
    '''
    This Pulse Audio Client acts as a buffer to store data we read from the mic.
    The bonus behind this is that it will collect the audio in a buffer, then use
    a dynamic generator to only yield the audio with speech detected.
    The collection of audio from the mic is done in a separate process to ensure
    we are always pulling the latest audio from the stream.
    '''

    FORMAT = pasimple.PA_SAMPLE_S16LE
    SAMPLE_WIDTH = pasimple.format2width(FORMAT)
    CHANNELS = 1
    SAMPLE_RATE = 16000
    BYTES_PER_SEC = CHANNELS * SAMPLE_RATE * SAMPLE_WIDTH

    def __init__(self, config: kizano.Config):
        self.config = config
        self._pool: list[mp.Process] = []
        self.listening = False
        self.vad_options = VadOptions(
            threshold=0.1,
            min_speech_duration_ms=450,
            max_speech_duration_s=float("inf"),
            min_silence_duration_ms=200,
            window_size_samples=1024,
            speech_pad_ms=250,
        )

    def _next_chunk(self, stream: pasimple.PaSimple) -> np.ndarray:
        '''
        Read the next chunk of audio from the stream.
        '''
        audio = np.frombuffer( stream.read(self.BYTES_PER_SEC), dtype=np.int16 ).astype(np.float32) / 32768.0
        return audio[~np.isnan(audio) & ~np.isinf(audio)]

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
            speech_prob, vad_state = vad(audio, vad_state, self.SAMPLE_RATE)
            if speech_prob > self.vad_options.threshold:
                silence = 0
                has_spoken = True
                log.info([random.choice(['uh-huh...', 'I hear you ...', 'yeap...'])])
                result = np.concatenate((result, audio), dtype=np.float32)
            else:
                if has_spoken:
                    silence += 1
                else:
                    log.debug("(I haven't heard you yet...).")
            audio = self._next_chunk(stream)
        log.info(f'Heard {silence} seconds of post-speech silence.')
        return result

    def streamWords(self, q: mp.Queue) -> int:
        '''
        Stream audio from the mic to a queue.
        '''
        stream = pasimple.PaSimple(pasimple.PA_STREAM_RECORD,
            self.FORMAT,
            self.CHANNELS,
            self.SAMPLE_RATE,
            app_name='asthralios',
            stream_name='asthralios-ears',
            maxlength=self.BYTES_PER_SEC * 2,
            fragsize=self.BYTES_PER_SEC // 5)
        while self.listening:
            audio = self.getSoundOfWords(stream, 2)
            q.put(audio)
        return 0

    def __del__(self):
        '''
        Clean up the pool of processes.
        '''
        for p in self._pool:
            p.terminate()
            p.join()

    def listen(self) -> Generator[np.ndarray, None, None]:
        '''
        @async -- This function starts PID's to listen, but does not join them until the program exits.
        Run self.doListen() in a subprocess and receive chunks via a queue to ensure we are always pulling the latest
        audio from the stream and storing it in a local buffer.
        '''
        self.listening = True
        q = mp.Queue()
        p = mp.Process(target=self.streamWords, args=(q,))
        p.start()
        self._pool.append(p)
        while self.listening:
            audio = q.get()
            yield audio

class LanguageCenter(object):
    '''
    Converts heard audio into something we can manage as text to interpret.
    '''
    def __init__(self, config: dict):
        self.config = config
        self.model = WhisperModel(
            config.get('whisper.model', os.getenv('WHISPER_MODEL', 'guillaumekln/faster-whisper-large-v2')),
            device=config.get('whisper.device', 'cuda'),
            compute_type=config.get('whisper.compute_type', 'auto'),
            cpu_threads=os.cpu_count(),
        )
        self.client = PulseClient(config)

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
        for audio in self.client.listen():
            yield self.toText(audio)

