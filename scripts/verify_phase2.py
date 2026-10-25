"""Lint the phase 2 contract against DDL text; does not execute PostgreSQL."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def table_bodies(sql):
    cleaned = re.sub(r'--[^\n]*', '', sql)
    tables = {}
    for match in re.finditer(r'CREATE\s+TABLE\s+([a-z_]+\.[a-z_]+)\s*\(', cleaned, re.I):
        index, depth, quoted = match.end(), 1, False
        start = index
        while index < len(cleaned) and depth:
            char = cleaned[index]
            if char == "'":
                if quoted and index + 1 < len(cleaned) and cleaned[index + 1] == "'":
                    index += 2
                    continue
                quoted = not quoted
            elif not quoted:
                depth += (char == '(') - (char == ')')
            index += 1
        if depth or quoted:
            raise ValueError('Unbalanced table definition: ' + match.group(1))
        name = match.group(1).lower()
        if name in tables:
            raise ValueError('Duplicate table declaration: ' + name)
        tables[name] = cleaned[start:index - 1]
    return tables


def columns(body):
    return set(re.findall(r'^\s*([a-z_]+)\s+(?:bigint|integer|smallint|text|char|numeric|uuid|jsonb|bytea|timestamp|timestamptz|date|boolean)\b', body, re.M | re.I))


def inspect_design(contract, sql):
    errors = []
    bodies = table_bodies(sql)
    actual_schemas = set(re.findall(r'CREATE\s+SCHEMA\s+(\w+)\s*;', sql, re.I))
    if actual_schemas != set(contract['schemas']):
        errors.append('Schema list differs from contract')
    if not sql.strip().startswith('-- New, empty LAK') or 'BEGIN;' not in sql or not sql.rstrip().endswith('COMMIT;'):
        errors.append('DDL must declare dedicated empty DB and one installation transaction')
    for table in list(contract['facts']) + list(contract['dimensions']) + [contract['bridge']['table']]:
        if table not in bodies:
            errors.append('Missing analytical table ' + table)
    for table, fact in contract['facts'].items():
        body = bodies.get(table, '')
        available = columns(body)
        for key in [fact['surrogate_key']] + fact['business_key']:
            if key not in available:
                errors.append(f'Missing key {table}.{key}')
        for field, target in fact['foreign_keys'].items():
            parent, key = target.rsplit('.', 1)
            pattern = rf'\b{re.escape(field)}\s+[^\n]*REFERENCES\s+{re.escape(parent)}\s*\(\s*{re.escape(key)}\s*\)'
            if not re.search(pattern, body, re.I):
                errors.append(f'FK differs from contract: {table}.{field} -> {target}')
            if key not in columns(bodies.get(parent, '')):
                errors.append('Referenced dimension key is absent: ' + target)
        for field in ('is_demo', 'is_deleted'):
            if field not in available:
                errors.append('Missing analysis filter ' + table + '.' + field)
        view = fact['analysis_view']
        if not re.search(rf'CREATE\s+VIEW\s+{re.escape(view)}\s+AS\s+SELECT\s+\*\s+FROM\s+{re.escape(table)}\s+WHERE\s+NOT\s+is_deleted\s+AND\s+NOT\s+is_demo', sql, re.I):
            errors.append('Analysis view does not exclude deleted/demo: ' + view)
    for table, dimension in contract['dimensions'].items():
        key = dimension['key']
        if key not in columns(bodies.get(table, '')):
            errors.append('Missing dimension key: ' + table)
        if not re.search(rf'INSERT\s+INTO\s+{re.escape(table)}\s*\([^;]+?\)\s*VALUES\s*\(0\s*,', sql, re.I | re.S):
            errors.append('Missing zero unknown member: ' + table)
    for name, source in contract['source_entities'].items():
        missing = set(source['fields']) - columns(bodies.get(source['staging_table'], ''))
        if missing:
            errors.append('Missing staging fields for ' + name + ': ' + ', '.join(sorted(missing)))
    required = [contract['cdc']['raw_table'], contract['cdc']['checkpoint_table'], contract['cdc']['ledger_table']]
    errors += ['Missing CDC storage ' + table for table in required if table not in bodies]
    if any(t.startswith(('mart.', 'ml.')) for t in bodies):
        errors.append('Phase 2 must reserve mart/ML schemas, not fabricate trained outputs')
    if 'EXCLUDE USING gist' not in sql or 'dim_product_one_current' not in sql:
        errors.append('SCD2 interval/current-version constraints missing')
    if re.search(r'\b(?:real|double\s+precision|float\d*)\b', '\n'.join(bodies.values()), re.I):
        errors.append('Floating-point column found in schema')
    if re.search(r'^\s*(?:customer_name|phone|full_address|driver_name)\s+', '\n'.join(bodies.values()), re.M | re.I):
        errors.append('Unnecessary personal field found in analytical schema')
    return errors, len(bodies)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    contract_path = ROOT / 'docs/phase2/data_contract.json'
    sql_path = ROOT / 'sql/phase2/001_warehouse_schema.sql'
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    errors, count = inspect_design(contract, sql_path.read_text(encoding='utf-8'))
    output = args.output_dir or ROOT / 'evidence/phase2' / ('design-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
    output.mkdir(parents=True, exist_ok=False)
    report = {'phase': 2, 'contract_version': contract['contract_version'],
              'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'passed': not errors, 'declared_tables': count, 'errors': errors,
              'sql_executed': False, 'powershell_executed': False,
              'needs_postgresql_schema_check': True,
              'input_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (contract_path, sql_path, ROOT / 'sql/phase2/002_schema_checks.sql', ROOT / 'scripts/test_phase2_postgres.ps1')}}
    (output / 'design-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for error in errors:
        print('ERROR: ' + error)
    print('Contract: ' + contract['contract_version'])
    print('Evidence: ' + str(output))
    print('PHASE 2 DESIGN CHECKS PASSED' if not errors else 'PHASE 2 DESIGN CHECKS FAILED')
    print('PostgreSQL execution is a separate required check; this is DDL/contract text lint only.')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
