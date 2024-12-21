# Archetype Similarity Index (ASI)

## Introduction

The Archetype Similarity Index (ASI) is a metric used to compare archetypes to a given decklist based on the unique number of card-pairings (bigrams) they share. This document explains how ASI is calculated and its components.

## Formula

The final similarity score for an archetype $A$ can be expressed as:

$$ S(A) = \frac{W_{\text{global}}(A) + W_{\text{local}}(A)}{\max\limits_{\substack{b=(c_1,c_2) \in B \\ c_1,c_2 \in D}} P(b)} $$

## Definitions

- **Bigrams ($B$)**: The set of all bigrams among the total pool of archetypes.
- **Decklist ($D$)**: The set of all cards in the decklist.
- **Joint Probability ($P(b | A)$)**: The joint hypergeometric probability of each card in bigram $b$ appearing in archetype $A$.
- **Maximum Joint Probability**: $\max\limits_{\substack{b=(c_1,c_2) \in B \\ c_1,c_2 \in D}} P(b)$ is the maximum joint hypergeometric probability for any bigrams in $D$.

## Weight Calculation

The summation is computed in two passes for $W_{\text{global}}$ and $W_{\text{local}}$:

- **Global Weight ($W_{\text{global}}$)**: The global weight of all bigrams in the archetype.
- **Local Weight ($W_{\text{local}}$)**: The local weight of bigrams that are unique to the archetype (among a pool of other archetypes with a high global weight).

We define the global and local weights as:

$$W_{\text{global}}(A) = \sum_{\substack{b=(c_1,c_2) \in B \\\\ c_1,c_2 \in D}} w_1(b,A) \cdot P(b | A)$$

$$W_{\text{local}}(A) = \sum_{\substack{b=(c_1,c_2) \in B \\\\ c_1,c_2 \in D}} w_2(b,A) \cdot P(b | A)$$

Where:

- $w_1(b,A)$ is the global weight of bigram $b$ in archetype $A$.
- $w_2(b,A)$ is the local weight of bigram $b$ in archetype $A$.

We can define the weights $w_1$ and $w_2$ as:

$$
w_1(b,A) =
\begin{cases}
2 & \text{if } A \in F \text{ and } \left| F \right| = 1 \\
1 & \text{otherwise}
\end{cases}
$$

$$
w_2(b,A) =
\begin{cases}
2 & \text{if } A \in C \cap F \text{ and } \left| F \right| = 1 \\
1 & \text{if } A \in C \cap F \text{ and } \left| F \right| < \frac{|C|}{3} \\
-1 & \text{if } A \notin C \text { and } A \in F \\
0 & \text{otherwise}
\end{cases}
$$

Where for all archetypes $A$:

- $C$ is the set of all candidate archetypes $A'$ such that $W_{\text{global}}(A') \geq M - 2$, where $M$ is the maximum score of $W_{\text{global}}$ among all archetypes.
- $|F|$ = $\left| \left\{ A' \in C \mid b \in A' \right\} \right|$, i.e. the
number of archetypes in $C$ that contain the bigram $b$.

## Normalized Joint Probability

The joint probability of a bigram (pair of cards) appearing in an opening hand is calculated using the hypergeometric distribution. This probability is then normalized by the maximum possible joint probability to ensure comparability across different bigrams and archetypes.

### Hypergeometric Probability

We define a variant of the hypergeometric probability function $\text{hypergeo}(k, N, n, m)$ as:

$$
\text{hypergeo}(k, N, n, m) = \sum_{i=n}^{\min(m, k)} \frac{\binom{m}{i} \binom{N-m}{k-i}}{\binom{N}{k}}
$$

where:

- $k$ is the number of successes in the hypergeometric distribution.
- $N$ is the total number of cards in the decklist.
- $n$ is the $\textit{minimum}$ number of successes in the draws.
- $m$ is the number of successes in the decklist.

For the sake of simplicity, we'll assume $N = 60$ and $n \geq 1$, though this
method generalizes for any arbitrary values of $N$ and $n$.

### Joint Probability

For a given archetype $A$, the probability of drawing both cards $c_1$, $c_2$ in a bigram $b$
is calculated as:

$$
P(b | A) = P(c_1 \cap c_2 | A) = P(c_1 | A) + P(c_2 | A) - P(c_1 \cup c_2 | A)
$$

where for archetype $A$:

- $P(c1 | A)$ is the probability of drawing at least one copy of card $c_1$.
- $P(c2 | A)$ is the probability of drawing at least one copy of card $c_2$.
- $P(c1 \cup c2 | A)$ is the probability of drawing at least one copy of either card $c_1$ or $c_2$.

Thus, we can define the probabilities $P(c_1 | A)$, $P(c_2 | A)$, and $P(c_1 \cup c_2 | A)$ as:

- $P(c_1 | A) = \text{hypergeo}(k_1, 60, n \geq 1, 7)$
- $P(c_2 | A) = \text{hypergeo}(k_2, 60, n \geq 1, 7)$
- $P(c_1 \cup c_2 | A) = \text{hypergeo}(k_1 + k_2, 60, n \geq 1, 7)$

where $k_1$ and $k_2$ are the counts of cards $c_1$ and $c_2$ in $A$, respectively.

### Normalization

The joint probability is normalized by the maximum possible joint probability:

$$
P_{\text{norm}} = \frac{P(x, y)}{P_{\text{MAX}}}
$$

where:

$$
P_{\text{MAX}} = 1 - \left(1 - \text{hypergeo}(k_{\text{max}}, 60, n \geq 1, 7)\right)^2
$$

Here, $k_{\text{max}} = \max\left(4, \frac{k_1 + k_2}{2}\right)$ is the maximum number of successes in the hypergeometric distribution. The maximum of 4 and the average of the counts of cards $c_1$ and $c_2$ is used to ensure that the maximum joint probability is not too small for large values of $k_1$ and $k_2$.
