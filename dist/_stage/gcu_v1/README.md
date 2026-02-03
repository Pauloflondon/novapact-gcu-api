# GCU v1 (Governed Classification Unit)

## Run
python gcu_v1/api/run.py --input "path\to\doc.txt"

## With metadata write (requires approval id)
python gcu_v1/api/run.py --input "path\to\doc.txt" --write-metadata --approval-id "APPROVAL-123"

## Kill switch
$env:GCU_KILL="true"
python gcu_v1/api/run.py --input "path\to\doc.txt"
Remove-Item Env:\GCU_KILL

## Selftest
python gcu_v1/tests/selftest.py
