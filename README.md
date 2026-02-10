# Learn RLHF Algorithms: PPO, DPO & GRPO

Educational implementations of the three main algorithms used to align large language models with human preferences.

**Pure NumPy — no PyTorch, no GPU needed.**

## Quick Start

```bash
pip install numpy
python rlhf_algorithms.py
```

The demo trains all three algorithms on a toy problem (learning to pick the correct action) and prints probability distributions at each stage so you can watch them converge.

## What's Inside

| File | Description |
|------|-------------|
| [`rlhf_algorithms.py`](rlhf_algorithms.py) | Annotated implementations of PPO, DPO, and GRPO with a runnable demo |
| [`index.html`](index.html) | Blog page with equations (KaTeX), intuition, and code walkthrough — [view as GitHub Pages](https://dragonfly90.github.io/learn_rlhf_algorithms/) |

## Algorithm Overview

| | PPO | DPO | GRPO |
|---|---|---|---|
| **Reward Signal** | Learned reward model | None — implicit in preference pairs | Rule-based or learned |
| **Critic / Value Net** | Yes | No | No — group-relative normalization |
| **Training Style** | RL loop: sample → score → clip → update | Supervised: learn from (chosen, rejected) pairs | RL loop: sample G → rank in group → clip → update |
| **Complexity** | High | Low | Medium |
| **Used By** | InstructGPT, early ChatGPT | Llama 2/3, Zephyr | DeepSeek-R1 |

## References

1. **PPO** — Schulman, J., Wolski, F., Dhariwal, P., Radford, A., & Klimov, O. (2017). *Proximal Policy Optimization Algorithms*. arXiv:1707.06347. [[paper]](https://arxiv.org/abs/1707.06347)

2. **InstructGPT (RLHF with PPO)** — Ouyang, L., Wu, J., Jiang, X., Almeida, D., Wainwright, C., Mishkin, P., Zhang, C., Agarwal, S., Slama, K., Ray, A., Schulman, J., Hilton, J., Kelton, F., Miller, L., Simens, M., Askell, A., Welinder, P., Christiano, P., Leike, J., & Lowe, R. (2022). *Training language models to follow instructions with human feedback*. NeurIPS 2022. arXiv:2203.02155. [[paper]](https://arxiv.org/abs/2203.02155)

3. **DPO** — Rafailov, R., Sharma, A., Mitchell, E., Ermon, S., Manning, C. D., & Finn, C. (2023). *Direct Preference Optimization: Your Language Model is Secretly a Reward Model*. NeurIPS 2023. arXiv:2305.18290. [[paper]](https://arxiv.org/abs/2305.18290)

4. **GRPO** — Shao, Z., Wang, P., Zhu, Q., Xu, R., Song, J., Zhang, M., Li, Y., Wu, Y., & Guo, D. (2024). *DeepSeekMath: Pushing the Limits of Mathematical Reasoning in Open Language Models*. arXiv:2402.03300. [[paper]](https://arxiv.org/abs/2402.03300)

5. **DeepSeek-R1 (GRPO at scale)** — DeepSeek-AI. (2025). *DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via Reinforcement Learning*. arXiv:2501.12948. [[paper]](https://arxiv.org/abs/2501.12948)

6. **RLHF foundations (Bradley-Terry model for preferences)** — Christiano, P., Leike, J., Brown, T., Marber, M., Shlegeris, B., & Irving, G. (2017). *Deep Reinforcement Learning from Human Preferences*. NeurIPS 2017. arXiv:1706.03741. [[paper]](https://arxiv.org/abs/1706.03741)

## License

MIT
