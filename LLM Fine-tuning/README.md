# LLM Fine-tuning

This project fine-tunes the **LLaMA 2** large language model to improve its **summarization capabilities** using the **QLoRA** (Quantized Low-Rank Adaptation) technique. We leverage the efficient [`Unsloth`](https://github.com/unslothai/unsloth) library to perform memory-optimized, fast, and scalable fine-tuning.

## Tools & Frameworks

* **Model**: LLaMA 2 (7B)
* **Fine-Tuning Technique**: QLoRA
* **Library**: [Unsloth](https://github.com/unslothai/unsloth) for efficient LoRA-based training
* **Evaluation**: BERTScore

## Highlights

* Fine-tuning is quantization-aware and memory-efficient.
* Ideal for running on consumer GPUs (e.g., 16GB VRAM).
* Pluggable with custom datasets for domain-specific summarization.
