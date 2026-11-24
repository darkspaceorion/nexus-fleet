# Science Officer report: Which local LLMs fit on a 12 GB RTX 3080 Ti for coding and general agent work, h

> **Status: needs NEXUS review.** Drafted by a local model. Not checked yet.
> Gate: **PASSED** - 5 sources read, 5 cited, 0 problems.
> Run: qwen3.5:9b, 83s, 7 model calls, 18,132 tokens in / 6,021 out (local, free). Job `20261116-211243-which-local-llms-fit-on-a-12-g`.

**Brief:** Which local LLMs fit on a 12 GB RTX 3080 Ti for coding and general agent work, how large are they on disk at Q4, and which do guides recommend most?

## Bottom line
Gemma 4 12B is the top coding pick for a 12 GB GPU with a download size of 7.7–8.0 GB [1]. Qwen 2.5 Coder 14B is also recommended as a solid code-specialised option using about 9 GB [1][3]. Both models fit within the VRAM limits when configured correctly [2][5].

## Findings
*   Gemma 4 12B uses approximately 8.02 GB of disk space and requires about 9.4 GB of VRAM at Q4_K_M quantization with a 65536 context window [2].
*   Qwen 2.5 Coder 14B uses approximately 8.99 GB of disk space and requires about 10.6 GB of VRAM at Q4_K_M quantization with an 8192 context window [2].
*   Ornith 9B is a smaller alternative that targets agentic coding with a download size of 5.6 GB [1].
*   DeepSeek-Coder-V2 Lite 16B fits in approximately 10 GB of VRAM and feels faster in the editor [3].
*   Qwen 3.5 9B fits on a 12 GB card at Q4_K_M quantization with about 8.8 GB used when set to 65536 context [2].
*   Codestral 22B does not fit in 12 GB VRAM as it requires approximately 13 GB [3].
*   The RTX 3080 Ti supports running LLMs up to 14 billion parameters when quantized to Q4 precision [4].

## Where sources disagree
*   Source [1] recommends Gemma 4 12B as the top coding model, while source [3] recommends Qwen 2.5 Coder 14B as the best local coding LLM for a 12 GB VRAM card [1][3].

## Gaps
*   The specific disk size at Q4 quantization for Phi-4 Reasoning Plus and K2 Horizon 7B was not provided in the sources [4].
*   The exact download sizes for Qwen 3.5 9B, DeepSeek-Coder-V2 Lite 16B, and GLM-6 9B were not explicitly stated as disk space figures in the notes provided [2][3][5].

## Sources
1. [Best Coding Model for 12 GB VRAM: Gemma 4 12B (2026)](https://www.promptquorum.com/prompt-bites/best-local-llm-coding-12gb-vram)
2. [Best Coding Model for 12GB VRAM: Ollama Picks That Fit](https://www.betterclaw.io/blog/best-coding-model-12gb-vram)
3. [Best Coding LLM for 12GB VRAM (2026): Local Models Ranked](https://localaimaster.com/vram/best-coding-llm-12gb-vram)
4. [Best LLMs to Run on NVIDIA RTX 3080 Ti (12GB) - VRAM & Benchmarks](https://apxml.com/hardware/rtx-3080ti-12gb) - dated undated
5. [Best Local LLMs for the NVIDIA GeForce RTX 3080 Ti (12 GB)](https://llmconfigurator.com/en/best-models/rtx-3080-ti)

<details><summary>Search log</summary>

Queries: local LLMs under 12 GB VRAM RTX 3080 Ti coding agent; best local LLM models for code generation 4-bit quantization disk size; recommended open source LLMs for general agent tasks small GPU


</details>
