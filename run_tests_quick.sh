#!/bin/bash
export PYTHONPATH=/home/kali/Downloads/NOC-coplite
cd /home/kali/Downloads/NOC-coplite
/home/kali/Downloads/NOC-coplite/venv/bin/python3 -m unittest \
    tests.test_path_decision \
    tests.test_failover_agent \
    tests.test_adaptive_failover \
    tests.test_federated_intelligence \
    2>&1 | tee /home/kali/Downloads/NOC-coplite/test_output.txt
echo "EXIT_CODE:$?"
