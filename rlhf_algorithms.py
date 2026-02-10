"""
Educational implementations of PPO, DPO, and GRPO for language model alignment.

Pure NumPy — no PyTorch, no GPU needed.

The "model" is a simple linear softmax policy (weights matrix mapping
states to action logits). Gradients are computed by hand so you can
see exactly what each algorithm is doing.

Requirements: just numpy  (pip install numpy)
"""

import numpy as np

np.random.seed(42)


# =====================================================================
# Shared: a minimal softmax policy  (replaces a full language model)
# =====================================================================
#
#   Policy:  π(a|s) = softmax(s @ W)[a]
#
#   W is a (state_dim × action_dim) weight matrix.
#   Think of "state" as a prompt embedding and "action" as a token choice.
# =====================================================================

class SoftmaxPolicy:
    def __init__(self, state_dim: int, action_dim: int):
        # Xavier init
        self.W = np.random.randn(state_dim, action_dim) * np.sqrt(2.0 / (state_dim + action_dim))

    def copy(self) -> "SoftmaxPolicy":
        p = SoftmaxPolicy.__new__(SoftmaxPolicy)
        p.W = self.W.copy()
        return p

    def logits(self, states: np.ndarray) -> np.ndarray:
        """Raw scores: (B, action_dim)"""
        return states @ self.W

    def probs(self, states: np.ndarray) -> np.ndarray:
        """Softmax probabilities: (B, action_dim)"""
        logits = self.logits(states)
        logits -= logits.max(axis=-1, keepdims=True)  # numerical stability
        exp = np.exp(logits)
        return exp / exp.sum(axis=-1, keepdims=True)

    def log_probs(self, states: np.ndarray, actions: np.ndarray) -> np.ndarray:
        """Log π(a|s) for each (state, action) pair. Returns shape (B,)."""
        p = self.probs(states)  # (B, action_dim)
        return np.log(p[np.arange(len(actions)), actions] + 1e-10)

    def sample(self, states: np.ndarray) -> np.ndarray:
        """Sample one action per state."""
        p = self.probs(states)
        return np.array([np.random.choice(len(row), p=row) for row in p])

    def grad_log_prob(self, states: np.ndarray, actions: np.ndarray) -> np.ndarray:
        """
        ∇_W log π(a|s)  — the policy gradient building block.

        For softmax:  ∇_W log π(a|s) = s^T (e_a - π(·|s))

        Returns shape (B, state_dim, action_dim) — one gradient per sample.
        """
        B = len(actions)
        p = self.probs(states)  # (B, action_dim)

        # One-hot for chosen actions
        one_hot = np.zeros_like(p)
        one_hot[np.arange(B), actions] = 1.0

        # (e_a - π): direction that increases log prob of action a
        diff = one_hot - p  # (B, action_dim)

        # Outer product: s^T (e_a - π) for each sample
        # states: (B, state_dim), diff: (B, action_dim)
        grads = states[:, :, None] * diff[:, None, :]  # (B, state_dim, action_dim)
        return grads

    def update(self, delta_W: np.ndarray):
        self.W += delta_W


# =====================================================================
# 1. PPO  —  Proximal Policy Optimization  (Schulman et al., 2017)
# =====================================================================
#
# Key idea:
#   Train a reward model, use it to score policy outputs, then update
#   the policy with a CLIPPED surrogate objective that prevents the
#   new policy from moving too far from the old one.
#
# Pipeline:
#   prompt → policy generates response → reward model scores it
#   → PPO clips the update to stay "proximal" to the old policy
#
# Used by: InstructGPT, early ChatGPT
# =====================================================================

def ppo_update(
    policy: SoftmaxPolicy,
    states: np.ndarray,         # (B, state_dim) — prompt embeddings
    actions: np.ndarray,        # (B,)           — sampled tokens
    old_log_probs: np.ndarray,  # (B,)           — log π_old(a|s) at sampling time
    advantages: np.ndarray,     # (B,)           — reward - baseline
    ref_log_probs: np.ndarray,  # (B,)           — log π_ref(a|s), frozen SFT model
    lr: float = 0.01,
    clip_eps: float = 0.2,
    kl_coeff: float = 0.1,
) -> float:
    """One PPO gradient step. Returns the loss value."""
    B = len(actions)

    # Current log probs and their gradients
    new_log_probs = policy.log_probs(states, actions)
    grad_lp = policy.grad_log_prob(states, actions)  # (B, state_dim, action_dim)

    # ---- Clipped surrogate objective ----
    #
    # ratio = π_new(a|s) / π_old(a|s)
    ratio = np.exp(new_log_probs - old_log_probs)  # (B,)

    # Unclipped and clipped objectives
    surr1 = ratio * advantages
    surr2 = np.clip(ratio, 1.0 - clip_eps, 1.0 + clip_eps) * advantages

    # Use the pessimistic (lower) bound
    # Gradient flows through surr1 when it's the min, zero otherwise
    use_unclipped = (surr1 <= surr2).astype(float)

    # ∇ ratio = ratio · ∇ log π  (since ratio = exp(log π_new - log π_old))
    # ∇ surr1 = advantages · ratio · ∇ log π
    # We want to MAXIMIZE, so gradient ascent → add
    ppo_grad_per_sample = (use_unclipped * advantages * ratio)[:, None, None] * grad_lp
    ppo_grad = ppo_grad_per_sample.mean(axis=0)

    # ---- KL penalty: keep policy near the reference (SFT) model ----
    # Approx KL:  exp(log π - log π_ref) - (log π - log π_ref) - 1
    log_diff = new_log_probs - ref_log_probs
    # ∇ KL ≈ (exp(log_diff) - 1) · ∇ log π
    kl_grad_per_sample = (np.exp(log_diff) - 1.0)[:, None, None] * grad_lp
    kl_grad = kl_coeff * kl_grad_per_sample.mean(axis=0)

    # Combined update: ascend on objective, descend on KL
    policy.update(lr * (ppo_grad - kl_grad))

    # Return scalar loss for logging
    loss = -np.minimum(surr1, surr2).mean() + kl_coeff * (np.exp(log_diff) - log_diff - 1).mean()
    return float(loss)


# =====================================================================
# 2. DPO  —  Direct Preference Optimization  (Rafailov et al., 2023)
# =====================================================================
#
# Key idea:
#   Skip the reward model entirely! Work directly with preference pairs:
#     (y_w = chosen/preferred,  y_l = rejected/dis-preferred)
#
#   The loss increases the gap between chosen and rejected log-probs,
#   *relative to a frozen reference model*, using the Bradley-Terry model.
#
# Loss:
#   L = -log σ( β · [ (log π(y_w) - log π_ref(y_w))
#                    - (log π(y_l) - log π_ref(y_l)) ] )
#
# Intuition:
#   "Make chosen MORE likely (relative to ref) and rejected LESS likely."
#
# Used by: Llama 2/3, Zephyr, many open-source models
# =====================================================================

def dpo_update(
    policy: SoftmaxPolicy,
    ref_policy: SoftmaxPolicy,
    states: np.ndarray,             # (B, state_dim)
    chosen_actions: np.ndarray,     # (B,) — preferred responses
    rejected_actions: np.ndarray,   # (B,) — dis-preferred responses
    lr: float = 0.01,
    beta: float = 0.1,
) -> float:
    """One DPO gradient step. Returns the loss value."""
    B = len(chosen_actions)

    # Log-probs under learning policy
    lp_chosen = policy.log_probs(states, chosen_actions)
    lp_rejected = policy.log_probs(states, rejected_actions)

    # Log-probs under frozen reference policy
    ref_chosen = ref_policy.log_probs(states, chosen_actions)
    ref_rejected = ref_policy.log_probs(states, rejected_actions)

    # ---- The DPO loss ----
    # margin = how much more the policy prefers chosen over rejected,
    #          compared to what the reference model does
    margin = (lp_chosen - ref_chosen) - (lp_rejected - ref_rejected)
    logits = beta * margin

    # σ(x) = 1/(1+exp(-x)), and we want -log σ(logits)
    sigmoid = 1.0 / (1.0 + np.exp(-logits))
    loss = -np.log(sigmoid + 1e-10).mean()

    # ---- Gradient ----
    # ∇L = -β(1 - σ) · [∇ log π(y_w) - ∇ log π(y_l)]
    grad_chosen = policy.grad_log_prob(states, chosen_actions)      # (B, D, A)
    grad_rejected = policy.grad_log_prob(states, rejected_actions)  # (B, D, A)

    weight = -beta * (1.0 - sigmoid)  # (B,)
    grad = (weight[:, None, None] * (grad_chosen - grad_rejected)).mean(axis=0)

    # Gradient descent (minimize loss)
    policy.update(-lr * grad)

    return float(loss)


# =====================================================================
# 3. GRPO  —  Group Relative Policy Optimization  (Shao et al., 2024)
# =====================================================================
#
# Key idea:
#   For each prompt, sample a GROUP of G responses. Score them all,
#   then normalize the rewards *within the group*. The normalized score
#   IS the advantage — no critic/value network needed!
#
#     advantage_i = (reward_i - mean(rewards)) / std(rewards)
#
#   Then do a PPO-style clipped update using these group-relative advantages.
#
# Differences from PPO:
#   - No value network (critic) needed — huge simplification
#   - Multiple responses per prompt, ranked relatively
#   - Works great with rule-based rewards (e.g. "is the math answer correct?")
#
# Used by: DeepSeek-R1 (reasoning model)
# =====================================================================

def grpo_update(
    policy: SoftmaxPolicy,
    ref_policy: SoftmaxPolicy,
    prompt: np.ndarray,            # (1, state_dim) — single prompt
    group_size: int = 8,           # G — number of responses to sample
    reward_fn=None,                # function(actions) → rewards array
    lr: float = 0.01,
    clip_eps: float = 0.2,
    kl_coeff: float = 0.04,
) -> float:
    """One GRPO step for a single prompt. Returns the loss value."""

    # Repeat prompt G times
    states = np.tile(prompt, (group_size, 1))  # (G, state_dim)

    # Step 1: sample G responses from current policy
    actions = policy.sample(states)  # (G,)

    # Step 2: score each response
    rewards = reward_fn(actions)  # (G,)

    # Step 3: GROUP-RELATIVE normalization → advantages
    # This is the key GRPO insight: no critic needed!
    mean_r = rewards.mean()
    std_r = rewards.std() + 1e-8
    advantages = (rewards - mean_r) / std_r  # (G,)

    # Snapshot log-probs before update (the "old" policy)
    old_log_probs = policy.log_probs(states, actions)

    # Step 4: PPO-style clipped update with group advantages
    new_log_probs = policy.log_probs(states, actions)
    grad_lp = policy.grad_log_prob(states, actions)

    ratio = np.exp(new_log_probs - old_log_probs)
    surr1 = ratio * advantages
    surr2 = np.clip(ratio, 1.0 - clip_eps, 1.0 + clip_eps) * advantages
    use_unclipped = (surr1 <= surr2).astype(float)

    policy_grad = (use_unclipped * advantages * ratio)[:, None, None] * grad_lp
    policy_grad = policy_grad.mean(axis=0)

    # KL penalty vs reference
    ref_log_probs = ref_policy.log_probs(states, actions)
    log_diff = new_log_probs - ref_log_probs
    kl_grad = (kl_coeff * (np.exp(log_diff) - 1.0))[:, None, None] * grad_lp
    kl_grad = kl_grad.mean(axis=0)

    policy.update(lr * (policy_grad - kl_grad))

    loss = -np.minimum(surr1, surr2).mean() + kl_coeff * (np.exp(log_diff) - log_diff - 1).mean()
    return float(loss)


# =====================================================================
# Demo: train all three on a toy problem
# =====================================================================
#
# Task: the policy picks one of 4 actions. Action 2 is "correct."
#   - PPO: a reward model gives +1 for action 2, -1 otherwise
#   - DPO: preference pairs where action 2 is always preferred
#   - GRPO: a rule-based reward (+1 if action 2, else -1)
#
# Watch each algorithm learn to favor action 2.
# =====================================================================

def demo():
    STATE_DIM = 4
    ACTION_DIM = 4
    TARGET_ACTION = 2
    EPOCHS = 30

    def show_probs(policy, state, label):
        p = policy.probs(state.reshape(1, -1))[0]
        bar = " ".join(f"a{i}={p[i]:.3f}" for i in range(ACTION_DIM))
        print(f"  {label:>10s}: [{bar}]")

    # A fixed "prompt"
    state = np.array([1.0, 0.5, -0.5, 0.2])

    # ------------------------------------------------------------------
    print("=" * 65)
    print("PPO — Proximal Policy Optimization")
    print("=" * 65)
    print("  Setup: reward model gives +1 for correct action, -1 otherwise")
    print()

    policy = SoftmaxPolicy(STATE_DIM, ACTION_DIM)
    ref_policy = policy.copy()

    show_probs(policy, state, "before")
    for epoch in range(EPOCHS):
        s = np.tile(state, (16, 1))                # batch of 16, same prompt
        a = policy.sample(s)                        # sample from current policy
        old_lp = policy.log_probs(s, a)
        ref_lp = ref_policy.log_probs(s, a)
        rewards = np.where(a == TARGET_ACTION, 1.0, -1.0)
        advantages = rewards - rewards.mean()       # simple baseline
        loss = ppo_update(policy, s, a, old_lp, advantages, ref_lp)
        if epoch % 10 == 9:
            print(f"  epoch {epoch+1:3d}: loss={loss:.4f}")
            show_probs(policy, state, f"epoch {epoch+1}")
    print()

    # ------------------------------------------------------------------
    print("=" * 65)
    print("DPO — Direct Preference Optimization")
    print("=" * 65)
    print("  Setup: preference pairs where action 2 is always preferred")
    print()

    policy = SoftmaxPolicy(STATE_DIM, ACTION_DIM)
    ref_policy = policy.copy()

    show_probs(policy, state, "before")
    for epoch in range(EPOCHS):
        s = np.tile(state, (16, 1))
        chosen = np.full(16, TARGET_ACTION, dtype=int)        # always prefer action 2
        rejected = np.random.choice(                          # reject a random other
            [a for a in range(ACTION_DIM) if a != TARGET_ACTION], size=16
        )
        loss = dpo_update(policy, ref_policy, s, chosen, rejected)
        if epoch % 10 == 9:
            print(f"  epoch {epoch+1:3d}: loss={loss:.4f}")
            show_probs(policy, state, f"epoch {epoch+1}")
    print()

    # ------------------------------------------------------------------
    print("=" * 65)
    print("GRPO — Group Relative Policy Optimization")
    print("=" * 65)
    print("  Setup: rule-based reward (+1 if action=2, else -1), group of 8")
    print()

    policy = SoftmaxPolicy(STATE_DIM, ACTION_DIM)
    ref_policy = policy.copy()

    def reward_fn(actions):
        return np.where(actions == TARGET_ACTION, 1.0, -1.0)

    show_probs(policy, state, "before")
    for epoch in range(EPOCHS):
        loss = grpo_update(
            policy, ref_policy,
            prompt=state.reshape(1, -1),
            group_size=8,
            reward_fn=reward_fn,
        )
        if epoch % 10 == 9:
            print(f"  epoch {epoch+1:3d}: loss={loss:.4f}")
            show_probs(policy, state, f"epoch {epoch+1}")
    print()

    # ------------------------------------------------------------------
    print("=" * 65)
    print("COMPARISON SUMMARY")
    print("=" * 65)
    print("""
  ┌────────────┬───────────────────┬───────────────────┬────────────────────┐
  │            │       PPO         │       DPO         │       GRPO         │
  ├────────────┼───────────────────┼───────────────────┼────────────────────┤
  │ Reward     │ Learned reward    │ None — implicit   │ Rule-based or      │
  │ signal     │ model (separate)  │ in preference     │ learned reward     │
  │            │                   │ pairs             │                    │
  ├────────────┼───────────────────┼───────────────────┼────────────────────┤
  │ Critic /   │ YES — needs a     │ NO                │ NO — group-relative│
  │ value net  │ value network     │                   │ normalization      │
  ├────────────┼───────────────────┼───────────────────┼────────────────────┤
  │ Training   │ RL loop:          │ Supervised:       │ RL loop (simpler): │
  │ style      │ sample → score    │ learn from        │ sample G responses │
  │            │ → clip → update   │ (chosen, rejected)│ → rank in group    │
  │            │                   │ pairs directly    │ → clip → update    │
  ├────────────┼───────────────────┼───────────────────┼────────────────────┤
  │ Data       │ Prompts +         │ Preference pairs  │ Prompts +          │
  │ needed     │ reward model      │ (y_w, y_l)        │ reward function    │
  ├────────────┼───────────────────┼───────────────────┼────────────────────┤
  │ Complexity │ High (RM + critic │ Low (one loss     │ Medium (no critic, │
  │            │ + policy + ref)   │ function)         │ but still RL loop) │
  ├────────────┼───────────────────┼───────────────────┼────────────────────┤
  │ Used by    │ InstructGPT,      │ Llama 2/3,        │ DeepSeek-R1        │
  │            │ early ChatGPT     │ Zephyr             │                    │
  └────────────┴───────────────────┴───────────────────┴────────────────────┘

  Key takeaway:
    PPO  = full RL pipeline, most general, most complex
    DPO  = supervised shortcut, elegant but needs preference pairs
    GRPO = simplified RL, no critic, great for verifiable rewards
    """)


if __name__ == "__main__":
    demo()
