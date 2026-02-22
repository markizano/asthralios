import os
from datasets import load_dataset, DatasetDict
from transformers import (
    WhisperTokenizer,
    WhisperProcessor,
    WhisperFeatureExtractor,
    WhisperForConditionalGeneration,
    Seq2SeqTrainingArguments,
    Seq2SeqTrainer
)
from datasets import Audio
from dataclasses import dataclass
from typing import Any, Dict, List, Union
 
import torch
import evaluate

model_id = 'openai/whisper-small'
out_dir = 'data/whisper_small_atco2'
epochs = 10
batch_size = 32

atc_dataset_train = load_dataset('jlvdoorn/atco2-asr-atcosim', split='train')
atc_dataset_valid = load_dataset('jlvdoorn/atco2-asr-atcosim', split='validation')


feature_extractor = WhisperFeatureExtractor.from_pretrained(model_id)
tokenizer = WhisperTokenizer.from_pretrained(model_id, language='English', task='transcribe')
processor = WhisperProcessor.from_pretrained(model_id, language='English', task='transcribe')

atc_dataset_train = atc_dataset_train.cast_column('audio', Audio(sampling_rate=16000))
atc_dataset_valid = atc_dataset_valid.cast_column('audio', Audio(sampling_rate=16000))

def prepare_dataset(batch):
    audio = batch['audio']
 
    batch['input_features'] = feature_extractor(audio['array'], sampling_rate=audio['sampling_rate']).input_features[0]
 
    batch['labels'] = tokenizer(batch['text']).input_ids
 
    return batch
 
atc_dataset_train = atc_dataset_train.map(
    prepare_dataset,
    num_proc=os.cpu_count()
)
 
atc_dataset_valid = atc_dataset_valid.map(
    prepare_dataset,
    num_proc=os.cpu_count()
)

@dataclass
class DataCollatorSpeechSeq2SeqWithPadding:
    processor: Any
    decoder_start_token_id: int
 
    def __call__(self, features: List[Dict[str, Union[List[int], torch.Tensor]]]) -> Dict[str, torch.Tensor]:
        input_features = [{'input_features': feature['input_features']} for feature in features]
        batch = self.processor.feature_extractor.pad(input_features, return_tensors='pt')
 
        label_features = [{'input_ids': feature['labels']} for feature in features]
        labels_batch = self.processor.tokenizer.pad(label_features, return_tensors='pt')
 
        labels = labels_batch['input_ids'].masked_fill(labels_batch.attention_mask.ne(1), -100)
 
        if (labels[:, 0] == self.decoder_start_token_id).all().cpu().item():
            labels = labels[:, 1:]
 
        batch['labels'] = labels
 
        return batch

model = WhisperForConditionalGeneration.from_pretrained(model_id)
model.generation_config.task = 'transcribe'
model.generation_config.forced_decoder_ids = None

data_collator = DataCollatorSpeechSeq2SeqWithPadding(
    processor=processor,
    decoder_start_token_id=model.config.decoder_start_token_id,
)

metric = evaluate.load('wer')
 
def compute_metrics(pred):
    pred_ids = pred.predictions
    label_ids = pred.label_ids
 
    # replace -100 with the pad_token_id
    label_ids[label_ids == -100] = tokenizer.pad_token_id
 
    # we do not want to group tokens when computing the metrics
    pred_str = tokenizer.batch_decode(pred_ids, skip_special_tokens=True)
    label_str = tokenizer.batch_decode(label_ids, skip_special_tokens=True)
 
    wer = 100 * metric.compute(predictions=pred_str, references=label_str)
 
    return {'wer': wer}

training_args = Seq2SeqTrainingArguments(
    output_dir=out_dir,
    per_device_train_batch_size=batch_size,
    per_device_eval_batch_size=batch_size,
    gradient_accumulation_steps=1,
    learning_rate=0.00001,
    warmup_steps=1000,
    bf16=True,
    fp16=False,
    num_train_epochs=epochs,
    eval_strategy='epoch',
    logging_strategy='epoch',
    save_strategy='epoch',
    predict_with_generate=True,
    generation_max_length=225,
    report_to=['tensorboard'],
    load_best_model_at_end=True,
    metric_for_best_model='wer',
    greater_is_better=False,
    dataloader_num_workers=8,
    save_total_limit=2,
    lr_scheduler_type='constant',
    seed=42,
    data_seed=42
)

trainer = Seq2SeqTrainer(
    args=training_args,
    model=model,
    train_dataset=atc_dataset_train,
    eval_dataset=atc_dataset_valid,
    data_collator=data_collator,
    compute_metrics=compute_metrics,
    processing_class=processor.feature_extractor,
)

trainer.train()
