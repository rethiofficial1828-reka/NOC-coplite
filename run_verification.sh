#!/bin/bash
export PYTHONPATH=/home/kali/Downloads/NOC-coplite
/home/kali/Downloads/NOC-coplite/venv/bin/python3 -m unittest \
    tests.test_path_decision \
    tests.test_failover_agent \
    tests.test_adaptive_failover \
    tests.test_federated_intelligence \
    > /home/kali/Downloads/NOC-coplite/verification_output.txt 2>&1
echo "FINISHED WITH EXIT STATUS $?" >> /home/kali/Downloads/NOC-coplite/verification_output.txt
