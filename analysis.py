"""
India Budget 2020 economic analysis.
Parses budget allocation data, computes sector-wise trends, and evaluates fiscal ratios.
"""
import json
import warnings
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")


SECTOR_MAPPING = {
    "agriculture": ["agriculture", "rural", "irrigation", "fertilizer", "food subsidy"],
    "education": ["education", "school", "higher education", "skill development"],
    "health": ["health", "ayushman", "medical", "nutrition"],
    "infrastructure": ["roads", "railways", "highways", "metro", "ports", "airports"],
    "defence": ["defence", "military", "border", "paramilitary"],
    "social_welfare": ["welfare", "women", "child", "scheduled caste", "scheduled tribe", "minority"],
    "energy": ["power", "solar", "petroleum", "coal", "electricity"],
    "finance": ["interest payments", "debt", "subsidies", "tax", "revenue"],
}


class BudgetParser:
    """Loads and normalizes budget allocation records."""

    def __init__(self, data: Optional[pd.DataFrame] = None):
        self.df = data.copy() if data is not None else pd.DataFrame()

    def load_from_records(self, records: List[Dict]) -> pd.DataFrame:
        self.df = pd.DataFrame(records)
        return self.df

    def normalize_columns(self) -> pd.DataFrame:
        """Standardize column names and numeric types."""
        rename = {}
        for col in self.df.columns:
            rename[col] = col.strip().lower().replace(" ", "_")
        self.df = self.df.rename(columns=rename)
        for col in self.df.select_dtypes(include="object").columns:
            if col not in ["ministry", "department", "scheme", "sector"]:
                try:
                    self.df[col] = pd.to_numeric(self.df[col].str.replace(",", ""), errors="coerce")
                except Exception:
                    pass
        return self.df

    def assign_sector(self) -> pd.DataFrame:
        """Map ministry/department names to macro sectors."""
        df = self.df
        if "ministry" not in df.columns and "department" not in df.columns:
            df["sector"] = "unclassified"
            return df
        name_col = "ministry" if "ministry" in df.columns else "department"

        def _map(name: str) -> str:
            name_lower = str(name).lower()
            for sector, keywords in SECTOR_MAPPING.items():
                if any(k in name_lower for k in keywords):
                    return sector
            return "other"

        df["sector"] = df[name_col].apply(_map)
        self.df = df
        return df


class BudgetAnalyzer:
    """
    Computes sector-wise allocation summaries, growth rates, fiscal ratios,
    and identifies priority shifts between budget years.
    """

    def __init__(self, df: pd.DataFrame, allocation_col: str = "allocation_cr",
                 year_col: Optional[str] = None):
        self.df = df
        self.allocation_col = allocation_col
        self.year_col = year_col

    def sector_summary(self, sector_col: str = "sector") -> pd.DataFrame:
        """Aggregate total allocation and share by sector."""
        if sector_col not in self.df.columns or self.allocation_col not in self.df.columns:
            raise ValueError(f"Missing columns: {sector_col}, {self.allocation_col}")
        grp = self.df.groupby(sector_col)[self.allocation_col].agg(["sum", "count"]).reset_index()
        grp.columns = [sector_col, "total_cr", "num_schemes"]
        total = grp["total_cr"].sum()
        grp["share_pct"] = (grp["total_cr"] / total * 100).round(2)
        return grp.sort_values("total_cr", ascending=False).reset_index(drop=True)

    def top_schemes(self, top_n: int = 10, scheme_col: str = "scheme") -> pd.DataFrame:
        """Return top N schemes by allocation."""
        if scheme_col not in self.df.columns or self.allocation_col not in self.df.columns:
            return pd.DataFrame()
        return (self.df[[scheme_col, self.allocation_col]]
                .sort_values(self.allocation_col, ascending=False)
                .head(top_n)
                .reset_index(drop=True))

    def year_over_year_growth(self, prev_year_col: str, curr_year_col: str,
                               group_col: str = "sector") -> pd.DataFrame:
        """Compute YoY percentage change in allocations by group."""
        if group_col not in self.df.columns:
            return pd.DataFrame()
        grp = self.df.groupby(group_col)[[prev_year_col, curr_year_col]].sum().reset_index()
        grp["yoy_growth_pct"] = ((grp[curr_year_col] - grp[prev_year_col]) /
                                  grp[prev_year_col].replace(0, np.nan) * 100).round(2)
        return grp.sort_values("yoy_growth_pct", ascending=False).reset_index(drop=True)

    def fiscal_ratios(self, gdp_cr: float) -> Dict:
        """Compute total expenditure / GDP and sector shares of GDP."""
        total = float(self.df[self.allocation_col].sum())
        ratios = {
            "total_expenditure_cr": round(total, 0),
            "expenditure_to_gdp_pct": round(total / gdp_cr * 100, 2),
        }
        if "sector" in self.df.columns:
            sector_totals = self.df.groupby("sector")[self.allocation_col].sum()
            for sector, amt in sector_totals.items():
                ratios[f"{sector}_to_gdp_pct"] = round(float(amt) / gdp_cr * 100, 4)
        return ratios

    def subsidy_analysis(self, subsidy_keywords: Optional[List[str]] = None) -> Dict:
        """Estimate total subsidy burden from scheme names containing subsidy keywords."""
        if subsidy_keywords is None:
            subsidy_keywords = ["subsidy", "dbt", "direct benefit"]
        if "scheme" not in self.df.columns:
            return {"total_subsidy_cr": 0.0, "subsidy_share_pct": 0.0}
        mask = self.df["scheme"].str.lower().str.contains("|".join(subsidy_keywords), na=False)
        total_subsidy = float(self.df.loc[mask, self.allocation_col].sum())
        total_all = float(self.df[self.allocation_col].sum())
        return {
            "total_subsidy_cr": round(total_subsidy, 0),
            "subsidy_share_pct": round(total_subsidy / total_all * 100, 2) if total_all > 0 else 0.0,
        }

    def capital_vs_revenue(self, type_col: str = "expenditure_type") -> Optional[pd.DataFrame]:
        """Break expenditure into capital vs revenue components."""
        if type_col not in self.df.columns:
            return None
        grp = self.df.groupby(type_col)[self.allocation_col].sum().reset_index()
        grp.columns = [type_col, "total_cr"]
        grp["share_pct"] = (grp["total_cr"] / grp["total_cr"].sum() * 100).round(2)
        return grp


if __name__ == "__main__":
    np.random.seed(42)
    n = 120
    sectors = list(SECTOR_MAPPING.keys()) + ["other"]
    records = [{
        "ministry": f"Ministry of {np.random.choice(['Agriculture', 'Education', 'Health', 'Roads', 'Defence', 'Power', 'Social Welfare', 'Finance'])}",
        "scheme": f"Scheme {i:03d} {'subsidy' if i % 10 == 0 else 'program'}",
        "allocation_2019_cr": float(np.random.lognormal(8, 1.5)),
        "allocation_2020_cr": float(np.random.lognormal(8.2, 1.5)),
        "expenditure_type": np.random.choice(["capital", "revenue"], p=[0.3, 0.7]),
    } for i in range(1, n + 1)]

    parser = BudgetParser()
    df = parser.load_from_records(records)
    parser.normalize_columns()
    parser.assign_sector()

    analyzer = BudgetAnalyzer(df=parser.df, allocation_col="allocation_2020_cr")
    print("Sector summary:")
    print(analyzer.sector_summary().to_string(index=False))

    print("\nTop 5 schemes by allocation:")
    print(analyzer.top_schemes(top_n=5, scheme_col="scheme").to_string(index=False))

    yoy = analyzer.year_over_year_growth(
        prev_year_col="allocation_2019_cr",
        curr_year_col="allocation_2020_cr",
    )
    print("\nYear-over-year growth by sector:")
    print(yoy.to_string(index=False))

    gdp_india_2020_cr = 19_500_000
    ratios = analyzer.fiscal_ratios(gdp_cr=gdp_india_2020_cr)
    print(f"\nTotal expenditure: {ratios['total_expenditure_cr']:,.0f} Cr")
    print(f"Expenditure/GDP: {ratios['expenditure_to_gdp_pct']}%")

    subsidy = analyzer.subsidy_analysis()
    print(f"\nSubsidy burden: {subsidy['total_subsidy_cr']:,.0f} Cr ({subsidy['subsidy_share_pct']}% of total)")

    cap_rev = analyzer.capital_vs_revenue()
    if cap_rev is not None:
        print("\nCapital vs Revenue split:")
        print(cap_rev.to_string(index=False))
