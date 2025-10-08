'''
Types for the Code Quality Checker.
'''

from pydantic import BaseModel, Field

SEVERITY_PATTERN = '^(info|low|medium|high|critical)$'

class CQCResult(BaseModel):
    name: str = Field(..., description='A succinct name for the quality check or issue.')
    severity: str = Field(..., description='The severity level of the issue identified.', pattern=SEVERITY_PATTERN)
    category: str = Field(..., description='The category of the issue. Example: injection, auth, encryption, secrets, acl, xsrf, xss, etc...')
    cwe: list[str] = Field(..., description='List of the CWE identifiers related to the issue. Example: ["CWE-80"]; empty list if unknown or not applicable.')
    cve: list[str] = Field(..., description='List of the CVE vulnerabilities. Example: ["CVE-1749:142"]; Empty list if unknown or not applicable.')
    owasp: list[str] = Field(..., description='The list of OWASP vulnerabilities. Empty list of not applicable.')
    lines: list[int, int] = Field(..., description='The starting and ending lines of the code snippet.')
    snippet: str = Field(..., description='The code snippet where the issue was found.')
    explanation: str = Field(..., description="A short explanation of the issue and why it's a problem.")
    remediation: str = Field(..., description='A short suggestion on how to fix the issue.')
    proposed_fix: str = Field(..., description='A minimal code diff on the suggested approach to fix the issue.')
    references: str = Field(..., description='List of relevant documentation links.')
    confidence: float = Field(..., description='A calibrated score between 0.0 and 1.0', ge=0.0, le=1.0)

class CQCResultSet(BaseModel):
    ok: bool = Field(..., description='Whether the code is good or not.')
    filename: str = Field(..., description='The filename where the issue was found.')
    issues: list[CQCResult] = Field(..., description='The list of issues found in the code.')

