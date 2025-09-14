"""
Flag type definitions for the Newstrack keyword automation system.
Defines the schema for flag objects that replace keyword removal.
"""
from typing import Dict, List, Optional, Union, Literal
from dataclasses import dataclass


# Flag types based on the specification
FlagType = Literal[
    "off_topic",           # Evidence is unrelated to the keyword
    "stale",               # Evidence is outside the recency window  
    "wrong_region",        # Evidence is from wrong region
    "region_scope_unmet",  # Can't satisfy region scope requirement
    "wrong_domain",        # Evidence is from wrong business domain (e.g. health vs P&C)
    "ambiguous_scope",     # Multiple regions found, unclear which is correct
    "weak_evidence",       # All evidence items are problematic
    "low_confidence"       # AI confidence in categorization is low
]

# Severity levels for flags
FlagSeverity = Literal["info", "warn", "block"]


@dataclass
class Flag:
    """
    Flag object schema for keyword issues.
    
    Replaces the removal system - keywords are kept but flagged with reasons.
    """
    type: FlagType
    severity: FlagSeverity
    reason: str                                    # Concise human explanation
    evidence_idx: Optional[List[int]] = None       # Which evidence_refs entries triggered it
    days_out_of_window: Optional[int] = None       # For stale flags
    expected_region: Optional[str] = None          # For region flags
    actual_region: Optional[str] = None            # Best-guess from source
    
    def to_dict(self) -> Dict:
        """Convert flag to dictionary for JSON serialization."""
        result = {
            "type": self.type,
            "severity": self.severity,
            "reason": self.reason
        }
        
        if self.evidence_idx is not None:
            result["evidence_idx"] = self.evidence_idx
        if self.days_out_of_window is not None:
            result["days_out_of_window"] = self.days_out_of_window
        if self.expected_region is not None:
            result["expected_region"] = self.expected_region
        if self.actual_region is not None:
            result["actual_region"] = self.actual_region
            
        return result


def create_flag(
    type: FlagType,
    severity: FlagSeverity, 
    reason: str,
    evidence_idx: Optional[List[int]] = None,
    days_out_of_window: Optional[int] = None,
    expected_region: Optional[str] = None,
    actual_region: Optional[str] = None
) -> Flag:
    """
    Factory function to create a Flag instance.
    
    Args:
        type: The type of flag
        severity: The severity level
        reason: Human-readable explanation
        evidence_idx: Optional list of evidence indices that triggered this flag
        days_out_of_window: For stale flags, how many days out of window
        expected_region: For region flags, what region was expected
        actual_region: For region flags, what region was found
        
    Returns:
        Flag instance
    """
    return Flag(
        type=type,
        severity=severity,
        reason=reason,
        evidence_idx=evidence_idx,
        days_out_of_window=days_out_of_window,
        expected_region=expected_region,
        actual_region=actual_region
    )


# Common flag creators for convenience
def create_off_topic_flag(reason: str, evidence_idx: Optional[List[int]] = None) -> Flag:
    """Create an off-topic flag."""
    return create_flag("off_topic", "block", reason, evidence_idx=evidence_idx)


def create_stale_flag(days_out: int, evidence_idx: Optional[List[int]] = None) -> Flag:
    """Create a stale flag."""
    return create_flag(
        "stale", 
        "warn", 
        f"Evidence is {days_out} days outside the recency window",
        evidence_idx=evidence_idx,
        days_out_of_window=days_out
    )


def create_wrong_region_flag(expected: str, actual: str, evidence_idx: Optional[List[int]] = None) -> Flag:
    """Create a wrong region flag."""
    return create_flag(
        "wrong_region",
        "warn", 
        f"Evidence from {actual}, expected {expected}",
        evidence_idx=evidence_idx,
        expected_region=expected,
        actual_region=actual
    )


def create_region_scope_unmet_flag(expected: str, reason: str) -> Flag:
    """Create a region scope unmet flag."""
    return create_flag(
        "region_scope_unmet",
        "warn",
        reason,
        expected_region=expected
    )


def create_wrong_domain_flag(reason: str, evidence_idx: Optional[List[int]] = None) -> Flag:
    """Create a wrong domain flag."""
    return create_flag("wrong_domain", "block", reason, evidence_idx=evidence_idx)


def create_weak_evidence_flag(reason: str = "All evidence items are problematic") -> Flag:
    """Create a weak evidence flag."""
    return create_flag("weak_evidence", "warn", reason)


def create_ambiguous_scope_flag(reason: str, actual_region: Optional[str] = None) -> Flag:
    """Create an ambiguous scope flag."""
    return create_flag(
        "ambiguous_scope", 
        "info", 
        reason,
        actual_region=actual_region
    )