# Current experiment metrics

[English](README.md) · [简体中文](README_ZH.md)

- [factor_comparison.csv](factor_comparison.csv): all 16 groups × Top5/10/20/30; validation and OOS metrics, risk, turnover, costs and actual Task / Run IDs.
- [yearly_comparison.csv](yearly_comparison.csv): yearly metrics for every group and TopN.
- [selection_decision.json](selection_decision.json): training-validation selection rule and selected task handles.
- [baseline_data_parity.json](baseline_data_parity.json): shared-field and complete prediction equality checks.
- [context_feature_coverage.csv](context_feature_coverage.csv): coverage of all 26 additions.
- [selected_feature_importance.csv](selected_feature_importance.csv): selected model feature importance.
- [training_parameters.json](training_parameters.json): model parameters, label, cutoff and selected rounds.

These compact summaries are included in the repository. Full daily artifacts and models remain in remote Tasks. Other experiment windows are preserved in [the historical archive](../archives/20261009/).
