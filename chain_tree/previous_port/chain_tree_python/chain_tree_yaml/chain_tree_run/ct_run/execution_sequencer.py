import yaml
from .chain_tree_run import ChainTreeRun
class ExecutionSequencer(ChainTreeRun):
    
    def __init__(self,yaml_file_name,wait_seconds=0.25,LispSequencer=None):
        ChainTreeRun.__init__(self,wait_seconds=wait_seconds,LispSequencer=LispSequencer)
        self.yaml_file_name = yaml_file_name
        self.load_yaml_file(self.yaml_file_name)
        self.kbs = self.python_dict["kb_log_dict"].keys()
        
    def list_kbs(self):
        return self.kbs
    
    def run_concurrent_tests(self,kb_list):
        for kb in kb_list:
            if kb not in self.kbs:
                raise ValueError(f"KB {kb} not found in yaml file {self.yaml_file_name}")
        self.run_multiple_kbs(kb_list)

    def run_sequencial_tests(self,kb_list):
        for kb in kb_list:
            if kb not in self.kbs:
                print(f"KB {kb} not found")
                raise ValueError(f"KB {kb} not found")
            self.run_multiple_kbs([kb])
            
    def run_all_test_sequentially(self):
        self.run_sequencial_tests(self.get_kb_list())

    def run_all_test_concurrently(self):
        self.run_concurrent_tests(self.get_kb_list())

