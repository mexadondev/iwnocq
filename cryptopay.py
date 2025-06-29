import aiohttp
from decimal import Decimal
from typing import Optional, Dict, List
import logging

class CryptoPayAPI:
    def __init__(self, api_token: str, testnet: bool = False):
        self.api_token = api_token
        self.base_url = "https://testnet-pay.crypt.bot/api" if testnet else "https://pay.crypt.bot/api"
        self.headers = {"Crypto-Pay-API-Token": api_token}

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict:
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method,
                f"{self.base_url}/{endpoint}",
                headers=self.headers,
                **kwargs
            ) as response:
                return await response.json()

    async def create_invoice(
        self,
        amount: str,
        asset: str = "USDT",
        description: Optional[str] = None,
        hidden_message: Optional[str] = None,
        paid_btn_name: Optional[str] = None,
        paid_btn_url: Optional[str] = None,
        payload: Optional[str] = None,
        allow_comments: bool = True,
        allow_anonymous: bool = True,
        expires_in: Optional[int] = None
    ) -> Dict:
        data = {
            "asset": asset,
            "amount": amount,
            "description": description,
            "hidden_message": hidden_message,
            "paid_btn_name": paid_btn_name,
            "paid_btn_url": paid_btn_url,
            "payload": payload,
            "allow_comments": allow_comments,
            "allow_anonymous": allow_anonymous,
            "expires_in": expires_in
        }
        return await self._make_request("POST", "createInvoice", json={k: v for k, v in data.items() if v is not None})

    async def transfer(
        self,
        user_id: int,
        asset: str,
        amount: str,
        spend_id: str,
        comment: Optional[str] = None,
        disable_send_notification: bool = False
    ) -> Dict:
        data = {
            "user_id": user_id,
            "asset": asset,
            "amount": amount,
            "spend_id": spend_id,
            "comment": comment,
            "disable_send_notification": disable_send_notification
        }
        return await self._make_request("POST", "transfer", json={k: v for k, v in data.items() if v is not None})

    async def create_check(
        self,
        amount: str,
        asset: str = "USDT",
        description: Optional[str] = None,
        hidden_message: Optional[str] = None,
        payload: Optional[str] = None,
        expires_in: Optional[int] = None
    ) -> Dict:
        data = {
            "asset": asset,
            "amount": amount,
            "description": description,
            "hidden_message": hidden_message,
            "payload": payload,
            "expires_in": expires_in
        }
        return await self._make_request("POST", "createCheck", json={k: v for k, v in data.items() if v is not None})

    async def get_balance(self) -> Dict:
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/getBalance"
                logging.info(f"Requesting balance from: {url}")
                
                async with session.get(
                    url,
                    headers=self.headers
                ) as response:
                    status = response.status
                    logging.info(f"Balance API response status: {status}")
                    
                    if status == 200:
                        data = await response.json()
                        logging.info(f"Raw balance response: {data}")
                        
                        if isinstance(data, dict) and 'result' in data:
                            for balance in data.get('result', []):
                                logging.info(f"Found currency: {balance.get('currency')}, available: {balance.get('available')}")
                            return data
                    else:
                        response_text = await response.text()
                        logging.error(f"API error status {status}: {response_text}")
                    
                    return {'result': []}
        except Exception as e:
            logging.error(f"CryptoPay API error: {e}")
            return {'result': []}

    async def get_exchange_rates(self) -> List[Dict]:
        response = await self._make_request("GET", "getExchangeRates")
        return response.get("result", [])

    async def get_invoices(self, status: str = None, offset: int = 0, count: int = 100) -> Dict:
        params = {
            "offset": offset,
            "count": count
        }
        if status:
            params["status"] = status
        return await self._make_request("GET", "getInvoices", params=params)

    async def get_checks(self, status: str = None, asset: str = None) -> Dict:
        """Получает список чеков. Можно фильтровать по статусу и валюте."""
        params = {}
        if status:
            params["status"] = status
        if asset:
            params["asset"] = asset
        return await self._make_request("GET", "getChecks", params=params) 