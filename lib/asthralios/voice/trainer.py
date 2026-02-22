from kizano import getLogger
log = getLogger(__name__)

log.info('hi!')

import os
import torch
import evaluate
from datasets import load_dataset, concatenate_datasets, Audio, Value, Features
from transformers import (
    WhisperForConditionalGeneration,
    WhisperProcessor,
    Seq2SeqTrainingArguments,
    Seq2SeqTrainer,
    WhisperTokenizer,
)
from peft import LoraConfig, get_peft_model
from torch.nn.utils.rnn import pad_sequence

### CONSTANTS ####
WHISPER_MODEL = 'openai/whisper-medium'  # or large-v2 if you have VRAM
DATA_DIR_WORDS = "data/samples/words"
DATA_DIR_PHRASES = "data/samples/phrases"
OUTPUT_DIR = "data/kizano-lora"

### FUNCTIONS ###
def map_text(e, idx, text_ds):
    e["text"] = text_ds[idx]["text"]
    return e

class KizanoDictionaryTrainer:

    def __init__(self):
        self.tokenizer = WhisperTokenizer.from_pretrained(WHISPER_MODEL)
        self.processor = WhisperProcessor.from_pretrained(WHISPER_MODEL, language='en')
        self.model = WhisperForConditionalGeneration.from_pretrained(WHISPER_MODEL).to('cuda')
        self.metric = evaluate.load("wer")
        log.info('Model & processor ready!')

        lora_cfg = LoraConfig(
            r=16,
            lora_alpha=32,
            lora_dropout=0.1,
            target_modules=['q_proj', 'v_proj'],
            task_type='SEQ_2_SEQ_LM'
        )
        log.info('LORA ready!')

        self.peft_model = get_peft_model(self.model, lora_cfg)
        log.info('Parameter-Efficient Fine-Tuning model ready!')


    def prepare(self, batch):
        # batch['audio'] is a dict: {'array': np.array, 'sampling_rate': int}
        audio = batch['audio']
        text = batch['text']

        # 1. Get input features from the audio
        input_features = self.processor.feature_extractor(
            audio['array'],
            sampling_rate=audio['sampling_rate']
        ).input_features  # shape: [1, seq_len, feature_dim]

        # 2. Tokenize text as labels
        labels = self.processor.tokenizer(
            text,
            return_tensors="pt",
            padding="longest"
        ).input_ids[0]

        return {
            "input_features": input_features,
            "labels": labels,
        }

    def data_collator(self, batch):
        input_features = [torch.tensor(x["input_features"]) for x in batch]
        labels = [torch.tensor(x["labels"]) for x in batch]

        # Pad input_features to same length along seq_len (dim=0)
        input_features_padded = pad_sequence(input_features, batch_first=True, padding_value=0.0)

        # Pad labels to same length
        log.debug(labels)
        # import code
        # code.interact(local=locals())
        labels_padded = pad_sequence(labels, batch_first=True, padding_value=-100)  # -100 is ignore_index for CrossEntropy

        return {
            "input_features": input_features_padded,
            "labels": labels_padded
        }

    def compute_metrics(self, pred):
        pred_ids = pred.predictions
        label_ids = pred.label_ids

        # replace -100 with the pad_token_id
        label_ids[label_ids == -100] = self.tokenizer.pad_token_id

        # we do not want to group tokens when computing the metrics
        pred_str = self.tokenizer.batch_decode(pred_ids, skip_special_tokens=True)
        label_str = self.tokenizer.batch_decode(label_ids, skip_special_tokens=True)
        wer = 100 * self.metric.compute(predictions=pred_str, references=label_str)

        return { "wer": wer }


    def load_training_data(self):
        log.info('Loading features & data set ...')
        features = Features({
            'audio': Audio(
                sampling_rate=16000,
                decode=True,
                num_channels=2,
            ),
            'text': Value('string')
        })

        twords = load_dataset('text', data_files=os.path.join(DATA_DIR_WORDS, '*.txt'), encoding='utf-8')['train']
        tphrases = load_dataset('text', data_files=os.path.join(DATA_DIR_PHRASES, '*.txt'), encoding='utf-8')['train']

        words = load_dataset(
            'audiofolder',
            data_dir=DATA_DIR_WORDS,
            features=features
        ).map(lambda x, idx: map_text(x, idx, twords), with_indices=True)
        phrases = load_dataset(
            'audiofolder',
            data_dir=DATA_DIR_PHRASES,
            features=features
        ).map(lambda x, idx: map_text(x, idx, tphrases), with_indices=True)

        dataset = concatenate_datasets([ words['train'], phrases['train'] ])
        log.info('Dataset ready!')
        return dataset

    def get_trainer(self):
        log.info('Processing samples...')
        processed = self.load_training_data().map(self.prepare)
        log.info('Samples iteratively processed!')

        training_args = Seq2SeqTrainingArguments(
            output_dir='data/kizano-lora',
            per_device_train_batch_size=6,
            gradient_accumulation_steps=4,
            fp16=True,
            learning_rate=1e-3,
            warmup_steps=50,
            max_steps=1400,       # enough for a small dataset
            save_steps=200,
            logging_steps=20,
            report_to='none',
            predict_with_generate=True,
        )

        trainer = Seq2SeqTrainer(
            model=self.model,
            args=training_args,
            data_collator=self.data_collator,
            compute_metrics=self.compute_metrics,
            train_dataset=processed,
            tokenizer=self.tokenizer,
        )

        return trainer

    def train_and_save(self):
        self.get_trainer().train()
        log.info('Model trained!')

        log.info('Saving results to checkpoint...')
        merged = self.processor.merge_and_unload()
        merged.save_pretrained('data/kizano-med')
        log.info('Complete!')

if __name__ == '__main__':
    KizanoDictionaryTrainer().train_and_save()
