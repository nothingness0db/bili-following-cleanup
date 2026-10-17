"""旧速率探针已停用；保留入口，避免旧指令继续发起压测。"""
import sys


def main():
    print("速率探针已停用，不发送任何网络请求。")
    print("离线自检：python selftest.py；查看本地暂停状态：python bili_read.py。")
    return 2


if __name__ == "__main__":
    sys.exit(main())
