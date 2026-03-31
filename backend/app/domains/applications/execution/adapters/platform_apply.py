"""Execution adapter for current platform.apply flow.

This is intentionally conservative: it wraps existing browser automation without
claiming deterministic browser outcomes. Determinism is limited to control-flow,
result shape, and failure classification.
"""

from __future__ import annotations

import re

from app.core.automation.platforms import platform_registry
from app.domains.applications.execution.adapters.base import (
    AdapterCapability,
    AdapterFailureClass,
    AdapterRisk,
    ArtifactRecord,
    ExecutionAdapter,
    ExecutionContext,
    ExecutionResult,
    VerificationResult,
)


class PlatformApplyAdapter(ExecutionAdapter):
    """Adapter for single-step submit via existing platform plugin apply()."""

    @property
    def capability(self) -> AdapterCapability:
        return AdapterCapability(
            adapter_name="platform_apply_v1",
            platforms=("linkedin", "indeed", "glassdoor"),
            supports_cover_letter=False,
            supports_multi_step_flows=False,
            risk=AdapterRisk.HIGH,
            deterministic_guarantees=(
                "bounded-execute-contract",
                "explicit-unsupported-manual-checkpoint",
                "failure-classification-no-silent-failure",
            ),
        )

    def supports(self, context: ExecutionContext) -> bool:
        return platform_registry.has(context.platform_name)

    async def prepare(self, context: ExecutionContext) -> ExecutionContext:
        # Keep prepare deterministic and side-effect-free for now.
        return context

    async def execute(self, context: ExecutionContext) -> ExecutionResult:
        if context.manual_checkpoint_mode:
            return ExecutionResult(
                success=False,
                submitted=False,
                needs_manual_checkpoint=True,
                error_code="MANUAL_CHECKPOINT",
                error_message=context.manual_checkpoint_reason
                or "manual checkpoint mode enabled",
                metadata={"mode": "manual_checkpoint"},
            )

        if not self.supports(context):
            return ExecutionResult(
                success=False,
                submitted=False,
                needs_manual_checkpoint=True,
                unsupported=True,
                error_code="UNSUPPORTED_PLATFORM",
                error_message=f"Unsupported execution adapter platform: {context.platform_name}",
                metadata={"platform": context.platform_name},
            )

        platform = platform_registry.create(context.platform_name)
        apply_output = await platform.apply(
            job=context.job_listing,
            resume_path=context.resume_path,
            cover_letter_path=context.cover_letter_path,
        )
        normalized = self._normalize_apply_output(apply_output, context)
        if not normalized["applied"]:
            return ExecutionResult(
                success=False,
                submitted=False,
                error_code="PLATFORM_APPLY_FAILED",
                error_message="Platform returned unsuccessful apply result",
                metadata=normalized["metadata"],
            )

        return ExecutionResult(
            success=True,
            submitted=True,
            metadata=normalized["metadata"],
        )

    def verify(self, result: ExecutionResult) -> VerificationResult:
        metadata = result.metadata or {}
        evidence = metadata.get("verification_evidence", {})
        platform = metadata.get("platform", "")
        text_blob = " ".join(
            [
                str(evidence.get("page_text", "")),
                " ".join([str(m) for m in evidence.get("text_markers", [])]),
            ],
        ).lower()
        current_url = str(evidence.get("current_url", "")).lower()
        dom_markers = [str(marker).lower() for marker in evidence.get("dom_markers", [])]
        submission_id = evidence.get("submission_id")

        failure_phrases = ("not submitted", "submission failed", "try again", "error submitting")
        if any(phrase in text_blob for phrase in failure_phrases):
            return VerificationResult(
                verified=False,
                classification="failed",
                reason="Confirmation page contains explicit failure signal",
                retryable=True,
                evidence=evidence,
            )

        success_phrase_hits = sum(phrase in text_blob for phrase in self._success_phrases(platform))
        dom_hits = sum(marker in marker_text for marker_text in dom_markers for marker in self._dom_markers(platform))
        url_hit = any(re.search(pattern, current_url) for pattern in self._url_patterns(platform))
        has_submission_id = bool(submission_id)

        strong_signal_count = int(url_hit) + int(dom_hits > 0) + int(success_phrase_hits > 0) + int(has_submission_id)
        if strong_signal_count >= 2 or (has_submission_id and (url_hit or success_phrase_hits > 0)):
            return VerificationResult(
                verified=True,
                classification="confirmed_success",
                evidence={
                    **evidence,
                    "signal_counts": {
                        "url_hit": url_hit,
                        "dom_hits": dom_hits,
                        "success_phrase_hits": success_phrase_hits,
                        "has_submission_id": has_submission_id,
                    },
                },
            )

        if result.success and result.submitted:
            return VerificationResult(
                verified=False,
                classification="uncertain",
                reason="Apply returned success but no strong confirmation evidence found",
                requires_manual_checkpoint=True,
                evidence=evidence,
            )

        return VerificationResult(
            verified=False,
            classification="failed",
            reason=result.error_message or "Execution did not submit application",
            retryable=True,
            evidence=evidence,
        )

    def collect_artifacts(self, result: ExecutionResult) -> list[ArtifactRecord]:
        verification_evidence = result.metadata.get("verification_evidence", {})
        artifacts = [
            ArtifactRecord(
                artifact_type="trace",
                storage_path=f"attempt://adapter/{self.capability.adapter_name}/trace",
                metadata={
                    "platform": result.metadata.get("platform", "unknown"),
                    "success": result.success,
                },
            ),
            ArtifactRecord(
                artifact_type="verification_evidence",
                storage_path=f"attempt://adapter/{self.capability.adapter_name}/verification",
                metadata=verification_evidence,
            ),
            ArtifactRecord(
                artifact_type="verification_bundle",
                storage_path=f"attempt://adapter/{self.capability.adapter_name}/verification_bundle",
                metadata={
                    "platform": result.metadata.get("platform", "unknown"),
                    "evidence_keys": sorted(list(verification_evidence.keys())),
                    "submitted": result.submitted,
                    "success": result.success,
                },
            ),
        ]
        if verification_evidence.get("screenshot_path"):
            artifacts.append(
                ArtifactRecord(
                    artifact_type="screenshot",
                    storage_path=f"attempt://adapter/{self.capability.adapter_name}/screenshot",
                    metadata={"path": verification_evidence.get("screenshot_path")},
                ),
            )
        if verification_evidence.get("dom_snapshot_path"):
            artifacts.append(
                ArtifactRecord(
                    artifact_type="dom_snapshot",
                    storage_path=f"attempt://adapter/{self.capability.adapter_name}/dom_snapshot",
                    metadata={"path": verification_evidence.get("dom_snapshot_path")},
                ),
            )
        if verification_evidence.get("execution_log"):
            artifacts.append(
                ArtifactRecord(
                    artifact_type="execution_log",
                    storage_path=f"attempt://adapter/{self.capability.adapter_name}/execution_log",
                    metadata={"log": verification_evidence.get("execution_log")},
                ),
            )
        if result.error_code:
            artifacts.append(
                ArtifactRecord(
                    artifact_type="log",
                    storage_path=f"attempt://adapter/{self.capability.adapter_name}/failure",
                    metadata={"error_code": result.error_code, "error_message": result.error_message or ""},
                ),
            )
        return artifacts

    def classify_failure(self, result: ExecutionResult) -> AdapterFailureClass:
        if result.success:
            return AdapterFailureClass.NONE
        if result.unsupported:
            return AdapterFailureClass.UNSUPPORTED
        if result.needs_manual_checkpoint or result.error_code == "MANUAL_CHECKPOINT":
            return AdapterFailureClass.MANUAL_CHECKPOINT
        return AdapterFailureClass.RETRYABLE

    def _normalize_apply_output(self, apply_output: object, context: ExecutionContext) -> dict[str, object]:
        evidence: dict[str, object] = {}
        applied = False

        if isinstance(apply_output, bool):
            applied = apply_output
        elif isinstance(apply_output, dict):
            applied = bool(apply_output.get("submitted"))
            evidence = {
                "current_url": apply_output.get("current_url"),
                "page_text": apply_output.get("page_text"),
                "dom_markers": apply_output.get("dom_markers", []),
                "text_markers": apply_output.get("text_markers", []),
                "submission_id": apply_output.get("submission_id"),
                "dom_snapshot_path": apply_output.get("dom_snapshot_path"),
            }

        if context.verification_hints:
            evidence = {**evidence, **context.verification_hints}

        metadata = {
            "platform": context.platform_name,
            "verification_evidence": evidence,
        }
        return {"applied": applied, "metadata": metadata}

    def _success_phrases(self, platform: str) -> tuple[str, ...]:
        common = (
            "application submitted",
            "your application has been submitted",
            "application sent",
            "thanks for applying",
        )
        platform_specific = {
            "linkedin": ("easy apply application submitted",),
            "indeed": ("application complete",),
            "glassdoor": ("application submitted successfully",),
        }
        return common + platform_specific.get(platform, ())

    def _dom_markers(self, platform: str) -> tuple[str, ...]:
        common = ("confirmation", "application-success", "submission-confirmation")
        platform_specific = {
            "linkedin": ("jobs-apply-modal", "artdeco-inline-feedback"),
            "indeed": ("ia-application-complete", "jobsearch-IndeedApplyButton"),
            "glassdoor": ("applicationConfirmation",),
        }
        return common + platform_specific.get(platform, ())

    def _url_patterns(self, platform: str) -> tuple[str, ...]:
        common = (r"/application[-_/]confirmation", r"/apply/complete", r"/submitted")
        platform_specific = {
            "linkedin": (r"linkedin\\.com/.*/jobs/.*/(complete|submitted)",),
            "indeed": (r"indeed\\.com/.*/apply.*(confirmation|complete)",),
            "glassdoor": (r"glassdoor\\.com/.*/application.*(complete|submitted)",),
        }
        return common + platform_specific.get(platform, ())
