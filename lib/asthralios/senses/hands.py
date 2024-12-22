
import os, io, sys
import json, yaml
import traceback as tb
import hashlib
from typing import Generator

from kizano import getLogger

from langchain_ollama.embeddings import OllamaEmbeddings
from langchain_postgres import PGVector
from langchain_core.documents import Document

from langchain_community.vectorstores.pgvector import PGVector

from langchain_community.document_loaders.json_loader import JSONLoader
from langchain_community.document_loaders.text import TextLoader
from langchain_community.document_loaders.pdf import PyPDFLoader
from langchain_community.document_loaders.markdown import UnstructuredMarkdownLoader
from langchain_community.document_loaders.html import UnstructuredHTMLLoader
from langchain_community.document_loaders.word_document import Docx2txtLoader
from langchain_community.document_loaders.powerpoint import UnstructuredPowerPointLoader
from langchain_community.document_loaders.excel import UnstructuredExcelLoader
from langchain_community.document_loaders.csv_loader import CSVLoader
from langchain_community.document_loaders.xml import UnstructuredXMLLoader

from langchain_text_splitters import RecursiveCharacterTextSplitter, RecursiveJsonSplitter

log = getLogger(__name__)

SUPPORTED_EXTS = [
    'txt',
    'pdf',
    'json',
    'md',
    'html',
    'htm',
    'doc',
    'docx',
    'ppt',
    'pptx',
    'xls',
    'xlsx',
    'csv',
    'xml',
    'yaml',
    'yml',
]

class Hands(object):
    '''
    Hands object to deal with reading various file types and ingesting them into the vector store.
    Communicates with an embeddings model in order to vectorize the text.
    Handles 3 main functions:
    - loadText: Given a path, return the Document() object.
    - splitText: Given a list of Document() objects, split the text into reasonable chunks.
    - ingest: Given a list of Document()s, injest into the vector store for searching later.

    :param config: Configuration object.
    '''

    def __init__(self, config: dict):
        self.config = config
        self.embeddings = OllamaEmbeddings(
            base_url=self.config['ollama']['url'],
            model=self.config['ollama']['embeddings'],
        )
        self.db = PGVector(
            embeddings=self.embeddings,
            connection=self.config['pgvector']['url'],
            collection_name=self.config['pgvector']['collection']
        )

    def recurseDirectory(self, path: str) -> Generator[str, None, None]:
        '''
        Given a path, recurse the directory tree and yield each file path.
        '''
        for root, dirs, files in os.walk(path):
            for file in files:
                yield os.path.join(root, file)

    def loadText(self, path: str) -> str:
        '''
        Given a path, return the Document() object for each file object read.
        '''
        ext = path.split('.')[-1]
        if ext == 'txt':
            loader = TextLoader(path, autodetect_encoding=True)
        elif ext == 'pdf':
            loader = PyPDFLoader(path)
        elif ext == 'json':
            loader = JSONLoader(path, jq_schema='.')
        elif ext in ['doc', 'docx']:
            loader = Docx2txtLoader(path)
        elif ext in ['ppt', 'pptx']:
            loader = UnstructuredPowerPointLoader(path)
        elif ext in ['xls', 'xlsx']:
            loader = UnstructuredExcelLoader(path)
        elif ext == 'csv':
            loader = CSVLoader(file_path=path, csv_args={
                'delimiter': ',',
                'quotechar': '"',
                'fieldnames': io.open(path).readline().strip().split(',')
            })
        elif ext == 'xml':
            loader = UnstructuredXMLLoader(path)
        elif ext == 'md':
            loader = UnstructuredMarkdownLoader(path)
        elif ext in ['html', 'htm']:
            loader = UnstructuredHTMLLoader(path)
        elif ext in ['yaml', 'yml']:
            data_structure = yaml.safe_load(open(path, 'r'))
            data = Document(page_content=json.dumps(data_structure), metadata={"source": path})
            return data
        documents = loader.load()
        [ doc.metadata.update({"type": ext}) for doc in documents ]
        return documents

    def splitText(self, data: list[Document]) -> list[Document]:
        '''
        Given a list of Document() objects, split the text into reasonable chunks.
        Return a mutated list of Document() objects containing the split chunks.
        '''
        result: list[Document] = []
        for doc in data:
            if doc.metadata['type'] in ['txt', 'md', 'html', 'htm', 'csv']:
                splitter = RecursiveCharacterTextSplitter()
                docs = splitter.split_documents([doc])
                result.extend(docs)
            elif doc.metadata['type'] in ['json', 'xml']:
                splitter = RecursiveJsonSplitter()
                docs = splitter.create_documents(doc.page_content, metadatas=doc.metadata)
                result.extend(docs)
            else:
                result.append(doc)
        return result

    def ingest(self, path: str) -> int:
        '''
        Given a path, search the directory tree for supported files.
        Injest into the vector store for searching later.
        '''
        for path in self.recurseDirectory(path):
            if path.split('.')[-1] in SUPPORTED_EXTS:
                loadedDocs = self.loadText(path)
                # log.debug({'texts': loadedDocs})
                docs = self.splitText( loadedDocs )
                # log.debug({'docs': docs})
                vdata = []
                texts = []
                metadatas = []
                for doc in docs:
                    if self.db.similarity_search(doc.page_content, k=1):
                        log.warning(f'Document {doc.metadata} already exists in the vector store.')
                        continue
                    vdata.extend(self.embeddings.embed_documents([doc.page_content]))
                    texts.append(doc.page_content)
                    metadatas.append(doc.metadata)
                if texts and vdata and metadatas:
                    self.db.add_embeddings(texts=texts, embeddings=vdata, metadatas=metadatas)
                    self.db.add_documents([Document(page_content=text, **meta) for text, meta in zip(texts, metadatas)])
                log.info(f'Ingested {path} with {len(vdata)} vectors.')
            else:
                log.warning(f'Unsupported file type: {path}')
        return 0

    def search(self, query: str) -> int:
        '''
        Given a query, search the vector store for similar documents.
        '''
        results = self.db.similarity_search_with_score(query, k=99)
        for result in results:
            log.debug([result[0].metadata, result[1]])
        log.info(f'Found {len(results)} results for query: {query}')
        return 0

    def clearVectorStore(self) -> int:
        '''
        Clear the vector store.
        '''
        self.db.delete_collection()
        return 0

def ingest(config: dict) -> int:
    '''
    Assume the config object contains all configuration and the intended command.
    Tee off the command and execute on injesting documents into the vector store.
    '''
    try:
        hands = Hands(config)
        return hands.ingest(config.get('path', '.'))
    except Exception as e:
        log.error(f'Error: {e}')
        log.error(tb.format_exc())
        return 1

if __name__ == '__main__':
    import kizano
    kizano.Config.APP_NAME = 'asthralios'
    config = kizano.getConfig()
    manos = Hands(config)
    command = os.environ.get('COMMAND', '')
    if command == 'search':
        sys.exit(manos.search(os.environ.get('QUERY', '')))
    elif command == 'clear':
        manos.clearVectorStore()
    else:
        sys.exit(manos.ingest(config.get('path', '.')))
