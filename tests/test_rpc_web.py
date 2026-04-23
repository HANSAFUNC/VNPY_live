"""RPC Web看板测试"""
import pytest
import asyncio
from unittest.mock import Mock, MagicMock, patch


class TestRpcWebEngine:
    """测试RPC Web引擎"""

    @pytest.fixture
    def mock_main_engine(self):
        """模拟MainEngine"""
        return Mock()

    @pytest.fixture
    def mock_event_engine(self):
        """模拟EventEngine"""
        return Mock()

    @pytest.fixture
    def mock_rpc_client(self):
        """模拟RpcClient"""
        with patch('vnpy.web.rpc_engine.RpcClient') as mock:
            yield mock

    def test_rpc_engine_init(self, mock_main_engine, mock_event_engine):
        """测试RPC引擎初始化"""
        from vnpy.web import RpcWebEngine

        engine = RpcWebEngine(
            main_engine=mock_main_engine,
            event_engine=mock_event_engine,
            req_address="tcp://test:2014",
            sub_address="tcp://test:2015"
        )

        assert engine.req_address == "tcp://test:2014"
        assert engine.sub_address == "tcp://test:2015"
        assert not engine._connected

    def test_rpc_connect_success(self, mock_main_engine, mock_event_engine, mock_rpc_client):
        """测试RPC连接成功"""
        from vnpy.web import RpcWebEngine

        engine = RpcWebEngine(
            main_engine=mock_main_engine,
            event_engine=mock_event_engine
        )

        result = engine.connect_rpc()

        assert result is True
        assert engine._connected is True
        mock_rpc_client.return_value.connect.assert_called_once()

    def test_rpc_connect_failure(self, mock_main_engine, mock_event_engine, mock_rpc_client):
        """测试RPC连接失败"""
        from vnpy.web import RpcWebEngine

        mock_rpc_client.return_value.connect.side_effect = Exception("连接失败")

        engine = RpcWebEngine(
            main_engine=mock_main_engine,
            event_engine=mock_event_engine
        )

        result = engine.connect_rpc()

        assert result is False
        assert engine._connected is False

    def test_get_account_data_connected(self, mock_main_engine, mock_event_engine):
        """测试获取账户数据（已连接）"""
        from vnpy.web import RpcWebEngine
        from vnpy.trader.object import AccountData

        engine = RpcWebEngine(
            main_engine=mock_main_engine,
            event_engine=mock_event_engine
        )
        engine._connected = True

        # 模拟返回账户
        mock_account = AccountData(
            gateway_name="TEST",
            accountid="12345",
            balance=100000.0,
            frozen=1000.0
        )
        mock_main_engine.get_all_accounts.return_value = [mock_account]

        result = engine._get_account_data()

        assert result["balance"] == 100000.0
        assert result["frozen"] == 1000.0

    def test_get_account_data_disconnected(self, mock_main_engine, mock_event_engine):
        """测试获取账户数据（未连接）"""
        from vnpy.web import RpcWebEngine

        engine = RpcWebEngine(
            main_engine=mock_main_engine,
            event_engine=mock_event_engine
        )
        engine._connected = False

        result = engine._get_account_data()

        assert result["balance"] == 0
        assert result["available"] == 0
