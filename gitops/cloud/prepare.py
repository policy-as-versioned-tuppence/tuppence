#!/usr/bin/env python3
"""Prepare only the cloud paths of tuppence's next signed composed artefact.

Requires an exact signed platform cloud tag and real vendor CRDs supplied
locally. No network, Provider, ProviderConfig or credentials are installed.
The fixture CRDs used for CLI replay are explicitly refused here.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import yaml

HERE = Path(__file__).resolve().parent
IDENTITY = r'^https://github\.com/policy-as-versioned-platform/platform/\.github/workflows/cloud-release\.yml@refs/heads/(main|release/[0-9]+\.[0-9]+\.x)$'
CRDS = {'instances.rds.aws.m.upbound.io', 'bucketserversideencryptionconfigurations.s3.aws.m.upbound.io'}


def prepare_crds(source: Path, destination: Path) -> list[dict]:
    docs = [doc for path in sorted(source.glob('*.yaml')) for doc in yaml.safe_load_all(path.read_text()) if doc]
    if {d.get('metadata', {}).get('name') for d in docs} != CRDS:
        raise ValueError('supply exactly the two real Upbound namespaced RDS/S3 CRDs')
    evidence = []
    destination.mkdir(parents=True, exist_ok=True)
    for doc in docs:
        if doc.get('kind') != 'CustomResourceDefinition' or doc['spec']['scope'] != 'Namespaced':
            raise ValueError('CRD-only namespaced install required')
        schema = next(v['schema']['openAPIV3Schema'] for v in doc['spec']['versions'] if v['name'] == 'v1beta1' and v['served'])
        provider = schema['properties']['spec']['properties']['forProvider']
        if provider.get('x-kubernetes-preserve-unknown-fields') or not provider.get('properties'):
            raise ValueError('offline fixture mapping is not a vendor field schema')
        if doc['metadata']['name'].startswith('bucket'):
            defaults = provider['properties']['rule']['items']['properties']['applyServerSideEncryptionByDefault']
            if defaults.get('type') != 'object' or 'sseAlgorithm' not in defaults.get('properties', {}):
                raise ValueError('vendor encryption field shape differs from this package; update and replay its CEL first')
        else:
            for key in ('multiAz', 'publiclyAccessible', 'storageEncrypted', 'backupRetentionPeriod'):
                if key not in provider['properties']:
                    raise ValueError('vendor RDS schema lacks dial ' + key)
        data = yaml.safe_dump(doc, sort_keys=False)
        name = doc['metadata']['name'] + '.yaml'
        (destination / name).write_text(data)
        evidence.append({'name': doc['metadata']['name'], 'sha256': hashlib.sha256(data.encode()).hexdigest()})
    (destination / 'kustomization.yaml').write_text(yaml.safe_dump({
        'apiVersion': 'kustomize.config.k8s.io/v1beta1', 'kind': 'Kustomization',
        'resources': [row['name'] + '.yaml' for row in evidence]}, sort_keys=False))
    return evidence


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--platform', type=Path, required=True)
    ap.add_argument('--tag', required=True)
    ap.add_argument('--commit', required=True)
    ap.add_argument('--vendor-crds', type=Path, required=True)
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
        spec = importlib.util.spec_from_file_location('cloud_render', package / 'render.py')
        assert spec is not None and spec.loader is not None, 'signed cloud package has no usable renderer'
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        resource_set = next(doc for doc in yaml.safe_load_all((HERE.parent / 'composed/composed-set.yaml').read_text()) if doc and doc.get('kind') == 'ResourceSet')
        claims = [row['version'] for row in resource_set['spec']['inputs'][0]['versions']]
        selected = {doc['metadata']['labels']['policy-as-versioned.dev/policy-version'] for doc in yaml.safe_load_all((HERE / 'claims.yaml').read_text()) if doc}
        if len(selected) != 1 or not selected <= set(claims):
            raise ValueError('cloud workload claim is not one of tuppence\'s composed versions')
        version = (package / 'VERSION').read_text().strip()
        docs = module.render(package, selected.pop(), 'tuppence', args.commit, claims)
        crds = prepare_crds(args.vendor_crds, args.output / 'cloud-crds')
        shutil.copyfile(package / 'cloud-rbac.yaml', args.output / 'cloud-crds/cloud-rbac.yaml')
        crd_membership = args.output / 'cloud-crds/kustomization.yaml'
        membership = yaml.safe_load(crd_membership.read_text())
        membership['resources'].append('cloud-rbac.yaml')
        crd_membership.write_text(yaml.safe_dump(membership, sort_keys=False))
        module.write_tree(args.output / 'cloud' / f'v{version}', docs)
        dest = args.output / 'cloud-workload'
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(HERE / 'claims.yaml', dest / 'claims.yaml')
        (dest / 'kustomization.yaml').write_text('apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources: [claims.yaml]\n')
        (args.output / 'CLOUD-PARENT.json').write_text(json.dumps({
            'party': 'platform', 'kind': 'implementations', 'name': 'cloud', 'tag': args.tag,
            'sha': args.commit, 'path': 'implementations/cloud', 'signature_identity': IDENTITY,
            'provider_crds': crds, 'proof_boundary': 'admission-only'}, indent=2) + '\n')


if __name__ == '__main__':
    main()
