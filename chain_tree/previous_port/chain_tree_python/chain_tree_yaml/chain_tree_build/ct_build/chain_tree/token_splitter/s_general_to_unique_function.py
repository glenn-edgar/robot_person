from .token_splitter import TokenSplitter

class SGeneralToUniqueFunction:
    """
    A class for converting a general function to a unique function.
    """
    def __init__(self,handle):
        self.chain_tree = handle
        self.token_splitter = TokenSplitter()
        
        
    def convert(self, input_string: str) -> dict:
        self.return_value = {}
        self.token_count = {}
        self.return_value["base_functions"] = {}
        self.return_value["unique_function"] = {}
        self.return_value["process_string"] = None
        
        
        self.processed_list = self.token_splitter.process(input_string, self.modify_tokens)
        
        self.return_value["process_string"] = self.processed_list[0]
        return self.return_value
    
    def modify_tokens(self, token: str) -> str:

        if token not in self.token_count:
            self.token_count[token] = 0
        else:
            self.token_count[token] += 1
        if token.startswith("@"):
            if token not in self.return_value["base_functions"]:
                self.return_value["base_functions"][token] = ["@",token]
            return_value = token + "_" + str(self.token_count[token])
            self.return_value["unique_function"][return_value] = ["@",token]
            return return_value
        elif token.startswith("?"):
            if token not in self.return_value["base_functions"]:
                self.return_value["base_functions"][token] = ["?",token]
            return_value = token + "_" + str(self.token_count[token])
            self.return_value["unique_function"][return_value] = ["?",token]
            return return_value
        
        elif token.startswith("!"):
            if token not in self.return_value["base_functions"]:
                self.return_value["base_functions"][token] = ["!",token]
            return_value = token + "_" + str(self.token_count[token])
            self.return_value["unique_function"][return_value] = ["!",token]
            return return_value
        else:
            raise ValueError(f"Invalid token: {token}")
    
    
if __name__ == "__main__":
    input_string = "(pipeline (?CFL_TIME_OUT 10) (@CFL_LOGM wait_for_three_seconds ) (!CFL_WAIT 3) (@CFL_LOGM wait_for_two_seconds)\
        (!CFL_WAIT 2) (@CFL_LOGM terminate_sequence) (@CFL_LOGM wait_five_seconds_for_timeout) 'CFL_HALT))"
    
    
    handle = {}
    s_general_to_unique_function = SGeneralToUniqueFunction(handle)
    return_value = s_general_to_unique_function.convert(input_string)
    
    print("process_string: " ,return_value["process_string"])
    print("base_functions: " ,return_value["base_functions"])
    print("unique_function: " ,return_value["unique_function"])
    print(return_value["unique_function"])