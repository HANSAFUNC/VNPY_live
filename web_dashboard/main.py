"""Web Dashboard 启动入口"""
import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description='VNPY Web Dashboard')
    parser.add_argument('--sub', default='tcp://localhost:2015',
                       help='RPC PUB 地址 (默认: tcp://localhost:2015)')
    parser.add_argument('--host', default='0.0.0.0',
                       help='Web 服务地址 (默认: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=8080,
                       help='Web 服务端口 (默认: 8080)')

    args = parser.parse_args()

    import dashboard.app as app_module
    app_module.data_manager.sub_address = args.sub

    print("=" * 60)
    print("VNPY Web Dashboard")
    print("=" * 60)
    print(f"RPC PUB 地址: {args.sub}")
    print(f"Web 地址: http://{args.host}:{args.port}")
    print("=" * 60)

    uvicorn.run("dashboard.app:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
