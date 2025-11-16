from kizano import getLogger
log = getLogger(__name__)

log.info('hi!')

import torch
from datasets import load_dataset, concatenate_datasets, Audio, Value, Features
from transformers import (
    WhisperForConditionalGeneration,
    WhisperProcessor,
    Seq2SeqTrainingArguments,
    Seq2SeqTrainer
)
from peft import LoraConfig, get_peft_model
from torch.nn.utils.rnn import pad_sequence


WHISPER_MODEL = 'openai/whisper-medium'  # or large-v2 if you have VRAM

log.info('Loading data set ...')
features = Features({
    'audio': Audio(
        sampling_rate=16000,
        decode=True,
        num_channels=2,
    ),
    'text': Value('string')
})

twords = load_dataset('text', data_files='data/samples/words/*.txt', encoding='utf-8')
tphrases = load_dataset('text', data_files='data/samples/phrases/*.txt', encoding='utf-8')

def map_words(e, idx):
    e['text'] = twords['train'][idx]['text']
    return e

def map_phrases(e, idx):
    e['text'] = tphrases['train'][idx]['text']
    return e

words = load_dataset('audiofolder', data_dir='data/samples/words', features=features).map(map_words, with_indices=True)
phrases = load_dataset('audiofolder', data_dir='data/samples/phrases', features=features).map(map_phrases, with_indices=True)

dataset = concatenate_datasets([ words['train'], phrases['train'] ])
log.info('Dataset ready!')

log.info('Loading model and processor...')
processor = WhisperProcessor.from_pretrained(WHISPER_MODEL)
model = WhisperForConditionalGeneration.from_pretrained(WHISPER_MODEL)
log.info('Model & processor ready!')

log.info('Setting up LORA Config...')
lora_cfg = LoraConfig(
    r=16,
    lora_alpha=32,
    lora_dropout=0.1,
    target_modules=['q_proj', 'v_proj'],
    task_type='SEQ_2_SEQ_LM'
)
log.info('LORA ready!')

eft_model = get_peft_model(model, lora_cfg)
log.info('PEFT model ready!')

def prepare(batch):
    # batch['audio'] is a dict: {'array': np.array, 'sampling_rate': int}
    audio = batch['audio']
    text = batch['text']

    # 1. Get input features from the audio
    input_features = processor.feature_extractor(
        audio['array'],
        sampling_rate=audio['sampling_rate']
    ).input_features  # shape: [1, seq_len, feature_dim]

    # 2. Tokenize text as labels
    labels = processor.tokenizer(
        text,
        return_tensors="pt",
        padding="longest"
    ).input_ids

    return {
        "input_features": input_features.squeeze(0),
        "labels": labels.squeeze(0),
    }

def data_collator(batch):
    input_features = [torch.tensor(x["input_features"]) for x in batch]
    labels = [torch.tensor(x["labels"]) for x in batch]

    # Pad input_features to same length along seq_len (dim=0)
    input_features_padded = pad_sequence(input_features, batch_first=True, padding_value=0.0)

    # Pad labels to same length
    labels_padded = pad_sequence(labels, batch_first=True, padding_value=-100)  # -100 is ignore_index for CrossEntropy

    return {
        "input_features": input_features_padded,
        "labels": labels_padded
    }

log.info('Processing samples...')
processed = dataset.map(prepare)
log.info('Samples iteratively processed!')

log.info('Training the model...')
training_args = Seq2SeqTrainingArguments(
    output_dir='data/kizano-lora',
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    fp16=True,
    learning_rate=1e-4,
    warmup_steps=50,
    max_steps=1400,       # enough for a small dataset
    save_steps=200,
    logging_steps=20,
    report_to='none',
    predict_with_generate=True,
)

trainer = Seq2SeqTrainer(
    model=eft_model,
    data_collator=data_collator,
    train_dataset=processed,
    args=training_args,
)

trainer.train()
log.info('Model trained!')

log.info('Saving results to checkpoint...')
merged = model.merge_and_unload()
merged.save_pretrained('data/kizano-med')
log.info('Complete!')
