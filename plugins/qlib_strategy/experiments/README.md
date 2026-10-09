# Current policy metrics

[English](README.md) · [简体中文](README_ZH.md)

- [policy_comparison.csv](policy_comparison.csv): both base/factor predictions × six minimum holding periods × Top5/10/20/30, with risk, turnover, costs and actual Task / Run IDs.
- [yearly_comparison.csv](yearly_comparison.csv): yearly metrics for every model, holding period and TopN.

The primary policy is predeclared at 10 days, `replacement_fraction=0.2` and `rank_buffer=1`. All rows use 0.05% buy / 0.15% sell fees. These compact summaries are included in the repository. Full daily artifacts remain in remote Tasks; other experiment windows are preserved in [the historical archive](../archives/20261009/).
