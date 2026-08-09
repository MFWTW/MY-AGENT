from dotenv import load_dotenv
load_dotenv()
import os
import appbuilder
from typing import Callable, Dict, Any


def search(query: str) -> Dict[str, Any]:
    """一个基于百度千帆的实战网页搜索引擎工具

    Args:
        query (str): _description_

    Returns:
        Dict[str, Any]: _description_
    """
    print(f"正在搜索: {query}")
    try:
        #从环境变量获取百度千帆的配置
        appbuilder_token = os.getenv("APPBUILDER_TOKEN")
        if not appbuilder_token:
            raise ValueError("请在环境变量中设置 APPBUILDER_TOKEN")
        
        #设置appbuilder的token
        os.environ["APPBUILDER_TOKEN"] = appbuilder_token
        
        #初始化搜索组件
        search_component = None
        
        #尝试多种方式初始化搜索组件
        #方式1: 使用 appbuilder.core.components.WebSearch
        try:
            search_component = appbuilder.core.components.WebSearch()
        except Exception as e:
            print(f"方式1初始化失败: {e}")
            pass
        


if __name__ == "__main__":
    toolExcutor = ToolExecutor()
    
    #注册我们的实战搜索工具
    search_description = "这是一个实战搜索工具，能够根据用户输入的关键词进行搜索，并返回相关的结果。"
    toolExcutor.register_tool("实战搜索", search_description, search_tool)
    
    #打印可用的工具
    print("可用的工具:")
    print(toolExcutor.getAvailableTools())