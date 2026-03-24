/**
 * WebSocket 自动重连工具
 *
 * 特性：
 * - 指数退避重连（1s → 2s → 4s → ... → 30s 上限）
 * - 连接/断开/错误状态回调
 * - 所有页面共用
 *
 * Usage:
 *   const conn = createReconnectingWS(
 *     `ws://${location.host}/ws/overview`,
 *     (data) => updateDisplay(data),
 *     {
 *       onOpen: () => setStatus('已连接'),
 *       onClose: () => setStatus('已断开'),
 *     }
 *   );
 *   // conn.close() to stop reconnecting
 */

function createReconnectingWS(url, onMessage, options) {
    options = options || {};
    const maxRetries = options.maxRetries || Infinity;
    const baseDelay = options.baseDelay || 1000;
    const maxDelay = options.maxDelay || 30000;

    let retries = 0;
    let ws = null;
    let stopped = false;

    function connect() {
        if (stopped) return;

        ws = new WebSocket(url);

        ws.onopen = function () {
            retries = 0;
            if (options.onOpen) options.onOpen();
        };

        ws.onmessage = function (event) {
            try {
                const data = JSON.parse(event.data);
                onMessage(data);
            } catch (e) {
                console.error('WebSocket 消息解析错误:', e);
            }
        };

        ws.onclose = function () {
            if (options.onClose) options.onClose();
            if (!stopped && retries < maxRetries) {
                const delay = Math.min(baseDelay * Math.pow(2, retries), maxDelay);
                retries++;
                setTimeout(connect, delay);
            }
        };

        ws.onerror = function (err) {
            if (options.onError) options.onError(err);
        };
    }

    connect();

    return {
        close: function () {
            stopped = true;
            if (ws) ws.close();
        },
        getWs: function () {
            return ws;
        },
    };
}
