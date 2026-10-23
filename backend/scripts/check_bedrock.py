"""Verify Amazon Bedrock access before selecting a runtime model.

    make check-bedrock                       # uses GHOSTSHIFT_BEDROCK_MODEL_ID / AWS_REGION
    uv run python scripts/check_bedrock.py --list
    uv run python scripts/check_bedrock.py --model us.<provider>.<model-id>

Checks, in order: AWS credentials resolve, the caller identity, which models /
inference profiles the account can see in the region, and a 5-token Converse
call against the chosen id. Prints actionable hints for the common failures
(no model access, inference profile required, missing IAM permission).
"""

from __future__ import annotations

import argparse
import sys

from ghostshift.config import get_settings
from ghostshift.integrations.base import ProviderError
from ghostshift.integrations.bedrock import BedrockConverseLLM


def main() -> int:
    s = get_settings()
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=s.bedrock_model_id)
    ap.add_argument("--region", default=s.aws_region)
    ap.add_argument("--list", action="store_true", help="List text models and inference profiles")
    args = ap.parse_args()

    try:
        import boto3

        session = boto3.Session(region_name=args.region)
        if session.get_credentials() is None:
            print("✗ No AWS credentials found (env vars, ~/.aws, SSO or instance role).")
            return 1
        ident = session.client("sts").get_caller_identity()
        print(f"✓ AWS identity: {ident['Arn']} (region {args.region})")
    except Exception as exc:  # noqa: BLE001
        print(f"✗ Could not resolve AWS identity: {exc}")
        return 1

    if args.list or not args.model:
        try:
            bedrock = session.client("bedrock")
            models = bedrock.list_foundation_models(byOutputModality="TEXT")["modelSummaries"]
            print(f"\nText models visible in {args.region} ({len(models)}):")
            for m in models:
                print(f"  {m['modelId']}  [{', '.join(m.get('inferenceTypesSupported', []))}]")
            profiles = bedrock.list_inference_profiles().get("inferenceProfileSummaries", [])
            print(f"\nInference profiles ({len(profiles)}):")
            for p in profiles:
                print(f"  {p['inferenceProfileId']}")
            print("\nModels listing only INFERENCE_PROFILE must be called via a profile id.")
        except Exception as exc:  # noqa: BLE001
            print(f"! Could not list models (needs bedrock:ListFoundationModels): {exc}")
        if not args.model:
            print("\nSet GHOSTSHIFT_BEDROCK_MODEL_ID (or pass --model) to test a Converse call.")
            return 0

    llm = BedrockConverseLLM(model_id=args.model, region=args.region, timeout_s=30)
    try:
        r = llm.complete("Reply with the single word OK.", "ping", max_tokens=64)
    except ProviderError as exc:
        print(f"✗ Converse failed for {args.model}: {exc}")
        return 2
    print(f"✓ Converse OK with {args.model} in {r.latency_ms:.0f} ms: {r.text.strip()!r}")
    print("  Set GHOSTSHIFT_MODE=auto (fallback on failure) or aws (failures reported) to use it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
