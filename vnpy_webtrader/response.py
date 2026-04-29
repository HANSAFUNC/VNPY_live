"""API 统一响应格式模块

提供泛型响应类型和构建工具函数，统一所有 API 的返回格式。
"""
from typing import Generic, TypeVar, Optional
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """错误详情"""
    code: str
    message: str


T = TypeVar('T')


class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应格式

    所有 API 端点返回此类型，前端统一处理。

    Example:
        # 成功响应
        {
            "success": True,
            "data": [...]
        }

        # 错误响应
        {
            "success": False,
            "error": {
                "code": "NOT_FOUND",
                "message": "Resource not found"
            }
        }
    """
    success: bool
    data: Optional[T] = None
    error: Optional[ErrorDetail] = None


def success_response(data: T) -> ApiResponse[T]:
    """创建成功响应"""
    return ApiResponse(success=True, data=data)


def error_response(code: str, message: str) -> ApiResponse:
    """创建错误响应"""
    return ApiResponse(success=False, error=ErrorDetail(code=code, message=message))


# 预定义错误响应
class Errors:
    """常用错误响应"""

    @staticmethod
    def not_found(resource: str) -> ApiResponse:
        return error_response("NOT_FOUND", f"{resource} not found")

    @staticmethod
    def rpc_error(message: str = "RPC method not available") -> ApiResponse:
        return error_response("RPC_ERROR", message)

    @staticmethod
    def validation_error(message: str) -> ApiResponse:
        return error_response("VALIDATION_ERROR", message)

    @staticmethod
    def internal_error(message: str = "Internal server error") -> ApiResponse:
        return error_response("INTERNAL_ERROR", message)

    @staticmethod
    def unauthorized(message: str = "Unauthorized") -> ApiResponse:
        return error_response("UNAUTHORIZED", message)
