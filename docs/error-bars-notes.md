## Readings — the claims these intervals are used to defend

*Hand-written (`docs/error-bars-notes.md`), spliced into this generated document by
`experiments/bootstrap_ci.py --notes`. Every number quoted below is read off the tables that
follow; none is computed here.*

### Coverage

Seven columns are covered — every `results/qual_records_*.json` that exists: Claude-Sonnet,
Qwen-32B and Qwen-72B on both substrates, and Mistral-7B on external. **Mistral-7B v3 has no
per-item artefact** — no `qual_records_` file was written for that run — so that column cannot be given
intervals here and its differences remain n=1 and uninterval'd; nothing in the writeup should
claim otherwise.

### Scale of the instrument

The median 95% CI width on an **overall** delta is **12 pp** (n=100–120); on a **per-type cell**
it is **15 pp** (n=20, i.e. roughly ±7.5 pp), and one question in an n=20 cell moves that cell by
**5 pp**. So a per-type movement of one or two questions cannot be distinguished from resampling
noise by this benchmark, and no per-type reading in the writeup should be defended on a margin
below ~15 pp.

### 10.4's "at noise level" — UPHELD, now evidenced

10.4 wrote of the Mistral-7B external column that *"small-n movements on schema (C3 15→10) and
temporal (C3 20→10) are 1–2 questions on n=20 cells, at noise level"*. Measured: those cells are
`schema` C3 EA **10.0 [0.0, 25.0]** and `temporal` C3 EA **10.0 [0.0, 25.0]** — 25 pp-wide
intervals that both include zero, against movements of 5–10 pp. The claim stands; it is now
backed by an interval rather than asserted. The same width applies to every per-type cell in
every column, so the caveat generalises: **per-type cells are indicative, not evidential.**

### 10.7's "churn" — UPHELD, now evidenced

10.7 recorded one non-monotonicity, *"external C2 EX 37.0 < C1 40.0 — churn (12 lost / 9
gained)"*, and read it as churn rather than a C2 defect. Measured: Qwen-32B external overall
ΔEX C2−C1 = **−3.0 [−12.0, +6.0]** — the interval straddles zero, so the benchmark cannot
distinguish that ordering from a tie. Qwen-72B external shows the same shape (**−5.0
[−13.0, +2.0]**, and ambiguous EA **−8.8 [−21.2, +3.8]**). The honest statement is that on the
external substrate **C2 and C1 are indistinguishable at this n**, not that C2 regressed.

### Criterion #1 — ambiguous-subset EA, C3 > C2

Positive in **all seven columns and in both strata**, and the interval clears zero in five of the
seven on the headline stratum: Mistral-7B external **+8.8 [+3.7, +15.0]**, Qwen-32B external
**+21.2 [+11.2, +31.2]**, Qwen-32B v3 **+6.2 [+1.2, +12.5]**, Qwen-72B external **+16.2 [+7.5,
+26.2]**, Qwen-72B v3 **+10.0 [+2.5, +17.5]**. The two Claude-Sonnet columns are positive but
touch zero (**+6.2 [+0.0, +12.5]** external, **+5.0 [+0.0, +11.2]** v3) — indicative, not
evidential. Under abort exclusion two columns lose significance while keeping their sign
(Mistral-7B external **+4.7 [+0.0, +10.9]**, Qwen-72B v3 **+6.8 [+0.0, +13.5]**); the two Qwen-32B
columns and Qwen-72B external clear zero under **both** strata, and those three are the columns
on which criterion #1 is defended.

### Criterion #2 — monotonic C1 ≤ C2 ≤ C3

On the headline stratum the ordering holds on point estimates for **five of the seven columns**
on overall EX (all three v3 columns, plus Claude-Sonnet external and Mistral-7B external) and for
**six of seven** on ambiguous EA. Where it breaks it breaks at the **C2−C1** step on the external
substrate — Qwen-32B (−3.0 [−12.0, +6.0]) and Qwen-72B (−5.0 [−13.0, +2.0]; ambiguous EA −8.8
[−21.2, +3.8]) — and every offending margin spans zero, so what is defensible is "no measurable
C2−C1 effect on external", not a reversal. **The C3−C2 step is never negative on the headline
stratum in any column**; it goes negative only on Mistral-7B external under abort exclusion, where
it is also indistinguishable from zero (next section).

### Where the two strata disagree in sign — and which reading is defended

One column only: **Mistral-7B external, overall ΔEX C3−C2**, which is **+3.0 [−2.0, +8.0]** over
all items and **−1.2 [−6.1, +2.4]** with the 18 C2 / 5 C3 aborts removed. **Neither interval
excludes zero**, so the sign flip is not a contest between two findings — it is two readings of
the same non-result, and the defended statement is that **this column provides no evidence of a
C3−C2 execution-accuracy effect either way**. That is also the concrete demonstration of why the
abort stratum was added. On this column C2 aborts on 18 items and C3 on 5 (the 5 are a subset of
the 18); **C3 answers 4 of the 18 C2-abort items correctly, and C2 answers 0 of C3's 5** — so all
+4 pp of gross gain in the +3.0 pp headline margin comes from items C2 never generated a query
for, which is a decoding-robustness difference and not an effect of disambiguation. Pairing does
not cancel it precisely because the two conditions abort on different item counts. It is *not* a
licence to quote −1.2 pp: the excluded figure removes those items from the arithmetic, it does
not make C2 (`beam_k=1`) and C3 (`beam_k=5`) decode identically. Only a C2 re-run at `beam_k=5` with an argmax commit would, and that is GPU work
outside step 11.5.

Elsewhere the two strata agree in sign everywhere, and the abort-excluded overall ΔEX moves by
less than 1 pp in every column except Qwen-32B external (+16.0 → +12.8, −3.2 pp) — including the
two columns whose C2 and C3 abort counts are equal (Claude-Sonnet external 0/0, Qwen-72B external
11/11), where pairing already cancels the contribution as expected.

### Strongest interval in the project

Qwen-32B external, `temporal` cell, ΔEX C3−C2 = **+65.0 [+45.0, +85.0]** (abort-excluded
**+61.1 [+38.9, +83.3]**) — 13 of 20 questions fixed by detect-then-commit with the questions and
the schema linker unchanged. This is the one per-type cell whose margin is far larger than the
15 pp per-type noise floor, and it is significant under both strata.

### Training variance (part B) — not run

Part B of 11.5 (a second training seed) was **dropped**. Everything above is sampling variance
over questions only; **no column has any estimate of training stochasticity**, and the n=1
caveat on training remains in force wherever an adapter-to-adapter difference is discussed.
