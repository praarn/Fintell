from pydantic import BaseModel


class ResumeMetricsOut(BaseModel):
    transactions_total: int
    transactions_categorized: int
    categorization_by_method: dict[str, int]
    pct_categorized_deterministically: float
    pct_categorized_via_llm: float
    pct_statements_via_learned_profile: float
    distinct_bank_profiles: int
    total_statements_processed: int
    llm_batch_calls: int
    llm_merchants_categorized: int
    llm_estimated_cost_usd: float
    text_to_sql_questions: int
    text_to_sql_answered: int
    text_to_sql_match_rate: float
