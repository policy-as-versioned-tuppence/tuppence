#!/usr/bin/env python3
"""Prepare only the cloud paths of tuppence's next signed composed artefact.

Requires an exact signed platform cloud tag containing its pinned vendor CRDs.
No network, Provider, ProviderConfig or credentials are installed. Optional
locally supplied schema copies must have the exact same pinned source bytes.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import yaml

HERE = Path(__file__).resolve().parent
IDENTITY = r'^https://github\.com/policy-as-versioned-platform/platform/\.github/workflows/cloud-release\.yml@refs/heads/(main|release/[0-9]+\.[0-9]+\.x)$'


def incumbent_claims() -> list[dict]:
    """Conserve the three incumbent resources, changing only their local binding."""
    provenance = json.loads((HERE / 'INCUMBENT.json').read_text())
    raw = (HERE / provenance['source_snapshot']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != provenance['sha256']:
        raise ValueError('incumbent source snapshot differs from its pinned bytes')
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if blob != provenance['git_blob']:
        raise ValueError('incumbent source snapshot differs from its Git blob')
    expected = [doc for doc in yaml.safe_load_all(raw) if doc]
    changes = provenance['lift_changes']
    for doc in expected:
        metadata = doc['metadata']
        labels = metadata['labels']
        if metadata['namespace'] != changes['namespace']['from'] or labels.get(changes['claim_label']['from']) != changes['claim_version']['from']:
            raise ValueError('incumbent claim does not have the recorded original binding')
        metadata['namespace'] = changes['namespace']['to']
        del labels[changes['claim_label']['from']]
        labels[changes['claim_label']['to']] = changes['claim_version']['to']
    actual = [doc for doc in yaml.safe_load_all((HERE / 'claims.yaml').read_text()) if doc]
    if actual != expected:
        raise ValueError('cloud lift changed an incumbent resource outside namespace and policy claim')
    return actual


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--platform', type=Path, required=True)
    ap.add_argument('--tag', required=True)
    ap.add_argument('--commit', required=True)
    ap.add_argument('--vendor-crds', type=Path, help='Optional local copy of the exact schemas pinned inside the signed package')
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    if not re.fullmatch(r'cloud/v\d+\.\d+\.\d+', args.tag) or not re.fullmatch(r'[0-9a-f]{40}', args.commit):
        raise ValueError('requires a real cloud semver tag and full immutable commit')
    resolved = subprocess.check_output(['git', '-C', str(args.platform), 'rev-parse', args.tag + '^{commit}'], text=True).strip()
    if resolved != args.commit:
        raise ValueError('cloud tag disagrees with its pinned commit')
    subprocess.run(['gitsign', 'verify-tag', args.tag, '--certificate-identity-regexp=' + IDENTITY,
                    '--certificate-oidc-issuer=https://token.actions.githubusercontent.com'], cwd=args.platform,
                   env=dict(os.environ, GITSIGN_REKOR_MODE='offline'), check=True)
    with tempfile.TemporaryDirectory(prefix='tuppence-cloud-source-') as tmp:
        snapshot = Path(tmp)
        archive = subprocess.check_output(['git', '-C', str(args.platform), 'archive', args.commit, 'implementations/cloud'])
        subprocess.run(['tar', '-xf', '-', '-C', str(snapshot)], input=archive, check=True)
        package = snapshot / 'implementations/cloud'
        spec = importlib.util.spec_from_file_location('cloud_composition', package / 'composition.py')
        assert spec is not None and spec.loader is not None, 'signed cloud package has no usable composer'
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        resource_set = next(doc for doc in yaml.safe_load_all((HERE.parent / 'composed/composed-set.yaml').read_text()) if doc and doc.get('kind') == 'ResourceSet')
        claims = [row['version'] for row in resource_set['spec']['inputs'][0]['versions']]
        selected = {doc['metadata']['labels']['policy-as-versioned.dev/policy-version'] for doc in incumbent_claims()}
        if len(selected) != 1 or not selected <= set(claims):
            raise ValueError('cloud workload claim is not one of tuppence\'s composed versions')
        if args.vendor_crds:
            schema_spec = importlib.util.spec_from_file_location('cloud_schema', package / 'provider_schema.py')
            assert schema_spec is not None and schema_spec.loader is not None
            schema = importlib.util.module_from_spec(schema_spec)
            schema_spec.loader.exec_module(schema)
            schema.validate(args.vendor_crds, package)
        parent, files = module.build(package, HERE, 'tuppence', args.commit, claims)
        parent['signature_identity'] = IDENTITY
        files['CLOUD-PARENT.json'] = json.dumps(parent, indent=2) + '\n'
        for path, text in files.items():
            destination = args.output / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(text)


if __name__ == '__main__':
    main()
