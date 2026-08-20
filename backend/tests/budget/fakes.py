from daf.models.budget import BudgetCeiling


class FakeRunConfigProvider:
    def __init__(self, ceiling: BudgetCeiling) -> None:
        self._ceiling = ceiling

    def get_budget_ceiling(self, run_id: str) -> BudgetCeiling:
        return self._ceiling
