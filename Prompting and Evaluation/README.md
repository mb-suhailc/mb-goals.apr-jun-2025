# Prompting and Evaluation

This project showcases a collection of **prompt engineering techniques** applied to the **quantized LLaMA 2 13B** model. It demonstrates how different prompting strategies can significantly enhance the performance of LLMs across a variety of tasks and domains.

## Objectives

* Demonstrate core prompting methods like **zero-shot**, **few-shot**, **chain-of-thought**, and more.
* Apply prompts across multiple **real-world use cases**.
* Evaluate prompt quality using metrics like **ROUGE** and **BERTScore**.
* Share best practices and patterns for designing high-impact prompts.

## Prompting Techniques Demonstrated

| Technique                 | Description                                                             |
| ------------------------- | ----------------------------------------------------------------------- |
| **Zero-shot**             | Direct prompt without examples                                          |
| **Few-shot**              | Prompt with a few relevant examples                                     |
| **Chain-of-Thought**      | Step-by-step reasoning in prompts                                       |
| **Self-Consistency**      | Sampling multiple CoT answers and choosing the most consistent          |
| **Tree-of-Thought**       | Branching reasoning paths for complex problems                          |
| **Rephrase & Respond**    | Ask model to rephrase question before answering                         |
| **Chain-of-Verification** | Model verifies its own response through a series of verification steps  |

## Prompt Evaluation Methods

To assess prompt effectiveness, we use:

* **ROUGE** (Recall-Oriented Understudy for Gisting Evaluation): Measures text overlap between generated and reference summaries.
* **BERTScore**: Semantic similarity between generated output and reference using BERT embeddings.

## Tools & Libraries
* cuBLAS
* evaluate
* llama_cpp
* huggingface_hub
