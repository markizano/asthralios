# from dotenv import load_dotenv
# load_dotenv()

import os

from typing import Generator
from kizano import getLogger

from langchain_core.messages import HumanMessage, SystemMessage
from langchain.chat_models import init_chat_model

from asthralios.sentinel.prompts import CQC_SYSTEM_PROMPT, CQC_USER_PROMPT
from asthralios.sentinel.types import CQCResultSet, CQCResult

log = getLogger(__name__)

class CodeQualityChecker:
    def __init__(self, cfg: dict) -> None:
        model = cfg.get('model', 'gpt-oss:20b')
        provider = cfg.get('provider', 'ollama')
        self.llm = init_chat_model(
            model=model,
            model_provider=provider
        )
        self.cqc_llm = self.llm.with_structured_output(CQCResultSet)

    def walkCodebase(self, path: str) -> Generator[str, None, None]:
        '''
        Iterate the codebase and return the list of files to check.
        '''
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.endswith('.py'):
                    yield os.path.join(root, file)

    def examineCode(self, filename: str, code: str) -> CQCResult:
        '''
        Examine the code for vulnerabilities and code quality.
        '''
        log.info(f'Examining code for {filename}')
        messages = [
            SystemMessage(content=CQC_SYSTEM_PROMPT),
            HumanMessage(content=CQC_USER_PROMPT % locals())
        ]
        return self.cqc_llm.invoke(messages)

def check_code_quality(cfg: dict) -> int:
    log.info(f'Checking code quality for {cfg["path"]}')
    cqc = CodeQualityChecker(cfg)
    for filename in cqc.walkCodebase(cfg['path']):
        try:
            code = open(filename).read()
            result = cqc.examineCode(filename, code)
            # if result.name == 'OK':
            #     continue
            print(result.model_dump_json())
            #DEBUG
            break
        except Exception as e:
            import traceback as tb
            log.error(f'Error examining code: {e}')
            log.error(tb.format_exc())
            break
    return 0
