
from chain_tree_run.ct_run.execution_sequencer import ExecutionSequencer
from s_functions.lisp_sequencer import LispSequencer
from pathlib import Path
import yaml
from chain_tree_user_functions import MyUserFunctions



wait_seconds = .25
ex_sequencer = ExecutionSequencer(yaml_file_name="basic_tests.yaml",wait_seconds=wait_seconds,LispSequencer=LispSequencer)

my_user_functions = MyUserFunctions(execution_sequencer=ex_sequencer)


test_list = ex_sequencer.list_kbs()

ex_sequencer.run_sequencial_tests(test_list)
   