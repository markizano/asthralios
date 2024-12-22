#!/usr/bin/env python3

import os
import sys
from glob import glob
from pprint import pprint
from setuptools import setup

setup_opts = {
    'name'                : 'asthralios',
    # We change this default each time we tag a release.
    'version'             : '1.0.0',
    'description'         : "Markizano's Assistant",
    'long_description'    : ('My Personal Assistant. I will use this to be able to understand AI'
                             'and how to interact with it from a programming perspective. This will be my means to'
                             'de-Google my life and to be able to have a personal assistant that I know what trained it.'),
    'long_description_content_type': 'text/markdown',
    'author'              : 'Markizano Draconus',
    'author_email'        : 'support@markizano.net',
    'url'                 : 'https://markizano.net/',
    'license'             : 'GNU',

    'tests_require'       : ['pytest', 'unittest'],
    'install_requires'    : [
        'PyYAML>=6.0.1',
        'kizano',
        'ffmpeg-python',
        'nvidia-pyindex',
        'nvidia-cudnn',
        'nvidia-cublas-cu11',
        'nvidia-cublas-cu12',
        'nvidia-cuda-cupti-cu12',
        'nvidia-cuda-nvrtc-cu11',
        'nvidia-cuda-nvrtc-cu12',
        'nvidia-cuda-runtime-cu11',
        'nvidia-cuda-runtime-cu12',
        'nvidia-cudnn-cu11',
        'nvidia-cudnn-cu12',
        'nvidia-cufft-cu12',
        'nvidia-curand-cu12',
        'nvidia-cusolver-cu12',
        'nvidia-cusparse-cu12',
        'nvidia-nccl-cu12',
        'nvidia-nvjitlink-cu12',
        'nvidia-nvtx-cu12',
        'openai==1.43.0',
        'openai-whisper',
        'faster-whisper',
        'pasimple==0.0.3',
        'psycopg2==2.9.10',
        'unstructured==0.16.11',
        'numba==0.60.0',
        'langchain==0.2.15',
        'langchain-community==0.2.15',
        'langchain-core==0.2.37',
        'langchain-ollama==0.1.3',
        'langchain-postgres==0.0.9',
        'langchain-text-splitters==0.2.2',
        'TTS==0.22.0',
        'requests'
    ],
    'package_dir'         : { 'asthralios': 'lib/asthralios' },
    'packages'            : [
      'asthralios', 'asthralios.cli'
    ],
    'scripts'             : glob('bin/*'),
    'entry_points': {
      'console_scripts': [
        'asthralios = asthralios.cli:main'
      ],
    },
    'test_suite'          : 'tests',
}

try:
    import argparse
    HAS_ARGPARSE = True
except:
    HAS_ARGPARSE = False

if not HAS_ARGPARSE: setup_opts['install_requires'].append('argparse')

# I botch this too many times.
if sys.argv[1] == 'test':
    sys.argv[1] = 'nosetests'

if 'DEBUG' in os.environ: pprint(setup_opts)

setup(**setup_opts)

if 'sdist' in sys.argv:
    import gnupg, hashlib
    gpg = gnupg.GPG()
    for artifact in glob('dist/*.tar.gz'):
        # Detach sign the artifact in dist/ folder.
        fd = open(artifact, 'rb')
        checksums = open('dist/CHECKSUMS.txt', 'w+b')
        status = gpg.sign_file(fd, detach=True, output=f'{artifact}.asc')
        print(f'Signed {artifact} with {status.fingerprint}')

        # create a MD5, SHA1 and SHA256 hash of the artifact.
        for hashname in ['md5', 'sha1', 'sha256']:
            hasher = getattr(hashlib, hashname)()
            fd.seek(0,0)
            hasher.update(fd.read())
            digest = hasher.hexdigest()
            checksums.write(f'''{hashname.upper()}:
{digest} {artifact}

'''.encode('utf-8'))
            print(f'Got {artifact}.{hashname} as {digest}')
        checksums.seek(0, 0)
        chk_status = gpg.sign_file(checksums, detach=True, output=f'dist/CHECKSUMS.txt.asc')
        checksums.close()
        fd.close()
        print(f'Signed CHECKSUMS.txt with {chk_status.fingerprint}')

