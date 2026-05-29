from weni import Tool
from weni.context import Context
from weni.responses import TextResponse
import requests
import json
import re


class CreateCart(Tool):
    BASE_URL = "https://brastemp.myvtex.com"
    GET_ORDERFORM_URL = (
        f"{BASE_URL}/api/checkout/pub/orderForm?forceNewCart=true&sc=2"
    )
    SIMULATION_URL = (
        f"{BASE_URL}/api/checkout/pub/orderForms/simulation?RnbBehavior=0&sc=2"
    )
    ADD_ITEM_URL = (
        f"{BASE_URL}/api/checkout/pub/orderForm/{{order_form_id}}/items?sc=2"
    )
    UPDATE_ITEMS_URL = (
        f"{BASE_URL}/api/checkout/pub/orderForm/{{order_form_id}}/items/update?allowedOutdatedData=paymentData"
    )
    REMOVE_ALL_URL = (
        f"{BASE_URL}/api/checkout/pub/orderForm/{{order_form_id}}/items/removeAll?sc=2"
    )

    def execute(self, context: Context) -> TextResponse:
        action = str(context.parameters.get("action", "") or "").strip()
        order_form_id = self.get_parameter(
            context,
            "order_form_id",
            "orderFormId",
            "order_formid",
            "orderformid",
        )
        sku_id = self.get_parameter(context, "sku_id", "skuId", "sku")
        quantity = context.parameters.get("quantity") or context.parameters.get("qty")
        postal_code = self.get_parameter(context, "postal_code", "postalCode", "cep")
        cookie = self.get_parameter(context, "cookie", "Cookie")
        checkout_vtex_cookie = self.get_parameter(
            context,
            "checkout_vtex_cookie",
            "checkout.vtex.com",
            "checkout_vtex_com",
        )
        checkout_order_form_ownership = self.get_parameter(
            context,
            "CheckoutOrderFormOwnership",
            "checkoutOrderFormOwnership",
            "checkout_order_form_ownership",
        )
        product_items_raw = context.parameters.get("product_items", [])

        if not action:
            action = self.infer_action(
                order_form_id=order_form_id,
                sku_id=sku_id,
                product_items_raw=product_items_raw,
                postal_code=postal_code,
                checkout_order_form_ownership=checkout_order_form_ownership,
            )

        action = self.normalize_action(action)

        if action == "simulate":
            return self.simulate_cart(
                context,
                product_items_raw,
                postal_code,
                cookie,
                checkout_vtex_cookie,
            )

        if action == "add_item":
            if not order_form_id:
                return TextResponse(
                    data={
                        "error": "orderFormId não encontrado em contact fields. Execute 'simulate' primeiro.",
                        "debug_info": {
                            "contact_fields": context.contact.get("fields", {}),
                            "parameters": context.parameters,
                        },
                    }
                )
            return self.add_item(
                order_form_id,
                sku_id,
                quantity,
                checkout_order_form_ownership,
                checkout_vtex_cookie,
            )

        if action == "update_items":
            if not order_form_id:
                return TextResponse(
                    data={
                        "error": "orderFormId não encontrado em contact fields. Execute 'simulate' primeiro.",
                        "debug_info": {
                            "contact_fields": context.contact.get("fields", {}),
                            "parameters": context.parameters,
                        },
                    }
                )
            order_items = (
                context.parameters.get("order_items")
                or context.parameters.get("items")
                or []
            )
            return self.update_items(
                order_form_id,
                order_items,
                checkout_vtex_cookie,
            )

        if action == "remove_all":
            if not order_form_id:
                return TextResponse(
                    data={
                        "error": "orderFormId não encontrado em contact fields. Execute 'simulate' primeiro.",
                        "debug_info": {
                            "contact_fields": context.contact.get("fields", {}),
                            "parameters": context.parameters,
                        },
                    }
                )
            return self.remove_all_items(
                order_form_id,
                checkout_order_form_ownership,
                checkout_vtex_cookie,
            )

        return TextResponse(
            data={
                "error": "Ação inválida para create_cart. Use simulate, add_item, update_items ou remove_all."
            }
        )

    def infer_action(
        self,
        order_form_id: str,
        sku_id: str,
        product_items_raw,
        postal_code: str,
        checkout_order_form_ownership: str,
    ) -> str:
        if product_items_raw and postal_code:
            return "simulate"
        if order_form_id and sku_id:
            return "add_item"
        if order_form_id and checkout_order_form_ownership and not sku_id:
            return "remove_all"
        return ""

    def normalize_action(self, action: str) -> str:
        normalized = str(action or "").strip().lower()
        if normalized in [
            "simulate",
            "simular",
            "simulation",
            "simulação",
            "simulacao",
        ]:
            return "simulate"
        if normalized in [
            "add_item",
            "add",
            "adicionar",
            "adicionar_item",
            "additem",
        ]:
            return "add_item"
        if normalized in [
            "update_items",
            "update",
            "atualizar",
            "atualizar_itens",
            "updateitems",
        ]:
            return "update_items"
        if normalized in [
            "remove_all",
            "removeall",
            "remover_todos",
            "remover",
            "limpar",
            "clear",
        ]:
            return "remove_all"
        return normalized

    def get_parameter(self, context: Context, *names, default="") -> str:
        for name in names:
            value = context.parameters.get(name)
            if value:
                return str(value)

        contact_fields = context.contact.get("fields", {}) or {}
        if isinstance(contact_fields, dict):
            for name in names:
                value = contact_fields.get(name)
                if value:
                    return str(value)

        return default

    def normalize_postal_code(self, postal_code: str) -> str:
        if not postal_code:
            return ""
        return re.sub(r"\D", "", str(postal_code))

    def get_account_name(self) -> str:
        parsed = self.BASE_URL.replace("https://", "").replace("http://", "")
        if parsed.endswith(".myvtex.com"):
            return parsed.split(".")[0]
        return parsed.split(".")[0]

    def build_checkout_link(self, order_form_id: str) -> str:
        """Constrói a URL de checkout do VTEX no formato correto"""
        account_name = self.get_account_name()
        # URL final: https://brastemp.com.br/checkout/?orderFormId=xxxxx
        return f"https://{account_name}.com.br/checkout/?orderFormId={order_form_id}"

    def get_weni_token(self, context: Context) -> str:
        return (
            context.project.get("auth_token", "")
            or context.credentials.get("token_weni", "")
            or context.credentials.get("WENI_TOKEN", "")
        )

    def save_contact_fields(self, context: Context, fields: dict) -> dict:
        contact_urn = context.contact.get("urn", "")
        auth_token = self.get_weni_token(context)

        if not contact_urn or not auth_token:
            return {
                "saved": False,
                "reason": "missing_contact_urn_or_weni_token",
                "has_contact_urn": bool(contact_urn),
                "has_weni_token": bool(auth_token),
            }

        # Tenta múltiplos esquemas de autorização caso o token esteja correto mas o esquema esperado seja diferente.
        def mask(t: str) -> str:
            if not t:
                return ""
            t = str(t)
            if len(t) <= 8:
                return "*" * len(t)
            return t[:4] + "..." + t[-4:]

        url = "https://flows.weni.ai/api/v2/contacts.json"
        attempts = []

        auth_schemes = [
            ("Token", f"Token {auth_token}"),
            ("Bearer", f"Bearer {auth_token}"),
            ("Raw", auth_token),
        ]

        for label, auth_header in auth_schemes:
            headers = {"Content-Type": "application/json", "Authorization": auth_header}
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    params={"urn": contact_urn},
                    json={"fields": fields},
                    timeout=15,
                )
                status = resp.status_code
                body = self.safe_text(resp)
                attempts.append({"scheme": label, "status_code": status, "response_body": body})
                if 200 <= status < 300:
                    return {"saved": True, "status_code": status, "attempts": attempts}
                # if 4xx/5xx continue to next scheme
            except requests.exceptions.RequestException as error:
                status_code = None
                response_body = None
                if hasattr(error, "response") and error.response is not None:
                    status_code = error.response.status_code
                    response_body = self.safe_text(error.response)
                attempts.append({
                    "scheme": label,
                    "error": str(error),
                    "status_code": status_code,
                    "response_body": response_body,
                })

        # Se chegou aqui, todas as tentativas falharam
        return {
            "saved": False,
            "reason": "request_failed",
            "has_contact_urn": bool(contact_urn),
            "token_summary": mask(auth_token),
            "attempts": attempts,
        }

    def parse_items(self, raw_items):
        if isinstance(raw_items, str):
            raw_items = raw_items.strip()
            if not raw_items:
                return []
            try:
                parsed = json.loads(raw_items)
                if isinstance(parsed, list):
                    return parsed
                if isinstance(parsed, dict):
                    if "items" in parsed:
                        return parsed["items"]
                    if "orderItems" in parsed:
                        return parsed["orderItems"]
                    return [parsed]
            except json.JSONDecodeError:
                # Tentar extrair itens entre colchetes, mantendo sufixos como #1 dentro do token
                bracketed = re.findall(r"\[([^\]]+)\]", raw_items)
                if bracketed:
                    items = []
                    for group in bracketed:
                        items.extend(self.split_item_tokens(group))
                    return [item for item in items if item]

                # Caso comum: lista simples separada por vírgulas ou espaços
                tokens = re.split(r"[\s,;|]+", raw_items)
                items = [self.normalize_sku(token) for token in tokens if token]
                return [item for item in items if item]

        if isinstance(raw_items, dict):
            if "items" in raw_items:
                return raw_items["items"]
            if "orderItems" in raw_items:
                return raw_items["orderItems"]
            return [raw_items]

        if isinstance(raw_items, list):
            return raw_items

        return []

    def split_item_tokens(self, text: str):
        tokens = re.split(r"[\s,;|]+", text)
        return [self.normalize_sku(token) for token in tokens if token]

    def build_cookie_header(
        self,
        cookie: str = "",
        checkout_vtex_cookie: str = "",
        checkout_order_form_ownership: str = "",
    ) -> str:
        parts = []
        if cookie:
            parts.append(str(cookie).strip())
        if checkout_order_form_ownership:
            parts.append(
                f"CheckoutOrderFormOwnership={str(checkout_order_form_ownership).strip()}"
            )
        if checkout_vtex_cookie:
            parts.append(f"checkout.vtex.com={str(checkout_vtex_cookie).strip()}")
        return "; ".join(parts)

    def generate_order_form_id(self, session: requests.Session = None) -> dict:
        """Gera um novo orderFormId via GET request a VTEX e preserva cookies se receber uma session."""
        headers = {"Content-Type": "application/json"}
        response = self.perform_request(
            "GET", self.GET_ORDERFORM_URL, headers=headers, session=session
        )

        if response.get("status") == "success":
            response_data = response.get("response", {})
            order_form_id = None

            # Tentar várias chaves possíveis que a VTEX pode retornar
            if isinstance(response_data, dict):
                for key in ("id", "orderFormId", "orderForm", "order_form_id", "order_formId"):
                    if key in response_data and response_data.get(key):
                        order_form_id = response_data.get(key)
                        break
                # Possível aninhamento: { "orderForm": { "id": "..." } }
                if order_form_id is None and isinstance(response_data.get("orderForm"), dict):
                    order_form_id = response_data.get("orderForm", {}).get("id")

            if order_form_id:
                response["order_form_id"] = order_form_id
            else:
                response["debug_orderform_generation"] = {
                    "response_structure": list(response_data.keys()) if isinstance(response_data, dict) else type(response_data).__name__,
                    "full_response": response_data,
                }

        return response

    def perform_request(
        self,
        method: str,
        url: str,
        headers: dict,
        json_data=None,
        raw_data=None,
        session: requests.Session = None,
    ) -> dict:
        try:
            requester = session.request if session is not None else requests.request
            response = requester(
                method,
                url,
                headers=headers,
                json=json_data,
                data=raw_data,
                timeout=20,
            )
            response.raise_for_status()
            return {
                "status": "success",
                "status_code": response.status_code,
                "response": self.safe_json(response),
            }
        except requests.exceptions.RequestException as error:
            message = str(error)
            response_body = None
            status_code = None
            if hasattr(error, "response") and error.response is not None:
                status_code = error.response.status_code
                response_body = self.safe_text(error.response)
            return {
                "status": "error",
                "message": "Falha na requisição VTEX",
                "details": message,
                "status_code": status_code,
                "response_body": response_body,
            }

    def safe_json(self, response):
        try:
            return response.json()
        except ValueError:
            return None

    def safe_text(self, response):
        try:
            return response.text
        except Exception:
            return None

    def normalize_sku(self, sku_value: str) -> str:
        """Normaliza valores de SKU removendo colchetes e sufixos como #1, preservando o restante do ID."""
        if sku_value is None:
            return sku_value

        s = str(sku_value).strip()
        if not s:
            return s

        # Remove colchetes externos e mantém o conteúdo interno.
        if s.startswith("[") and s.endswith("]"):
            s = s[1:-1].strip()

        # Remove sufixo de instância (#1, #2, etc.) sem tocar no restante do SKU.
        s = re.sub(r"#\d+$", "", s).strip()

        return s

    def simulate_cart(
        self,
        context: Context,
        product_items_raw,
        postal_code: str,
        cookie: str,
        checkout_vtex_cookie: str,
    ) -> TextResponse:
        # Usar session para preservar cookies entre chamadas
        session = requests.Session()

        # Se o chamador forneceu cookies, aplicar no header da session
        if cookie or checkout_vtex_cookie:
            session.headers.update(
                {"Cookie": self.build_cookie_header(cookie=cookie, checkout_vtex_cookie=checkout_vtex_cookie)}
            )

        # Passo 1: Gerar novo orderFormId (essa request pode setar cookies na session)
        orderform_response = self.generate_order_form_id(session=session)
        if orderform_response.get("status") != "success":
            return TextResponse(
                data={
                    "error": "Falha ao gerar orderFormId. Não é possível simular o carrinho.",
                    "details": orderform_response,
                }
            )

        order_form_id = orderform_response.get("order_form_id")
        if not order_form_id:
            return TextResponse(
                data={
                    "error": "orderFormId não obtido da resposta VTEX.",
                    "debug": orderform_response.get("debug_orderform_generation"),
                }
            )

        # Passo 2: Validar dados de entrada
        if not postal_code:
            return TextResponse(
                data={"error": "CEP não informado. Por favor informe o CEP para simular o carrinho."}
            )

        postal_code = self.normalize_postal_code(postal_code)
        if not postal_code:
            return TextResponse(
                data={"error": "CEP inválido. Forneça apenas os números do CEP."}
            )

        sku_ids = self.parse_items(product_items_raw)
        if not sku_ids:
            return TextResponse(
                data={"error": "Nenhum SKU informado para a simulação do carrinho."}
            )

        items = []
        for sku in sku_ids:
            sku_value = str(sku).strip()
            if not sku_value:
                continue
            normalized = self.normalize_sku(sku_value)
            items.append({"id": normalized, "quantity": 1, "seller": "1"})

        if not items:
            return TextResponse(
                data={"error": "Nenhum SKU válido encontrado para simulação."}
            )

        # Passo 3: Fazer simulação com o orderFormId
        payload = {
            "items": items,
            "postalCode": postal_code,
            "country": "BRA",
        }
        headers = {"Content-Type": "application/json"}

        # Se houver cookies fornecidos explicitamente, mantê-los no headers da request
        if cookie or checkout_vtex_cookie:
            headers["Cookie"] = self.build_cookie_header(
                cookie=cookie,
                checkout_vtex_cookie=checkout_vtex_cookie,
            )

        simulation_url = self.SIMULATION_URL

        response = self.perform_request(
            "POST", simulation_url, headers=headers, json_data=payload, session=session
        )

        # Passo 4: Preparar resposta
        response["debug_simulate_cart"] = {
            "generated_order_form_id": order_form_id,
            "simulation_url": simulation_url,
            "payload": payload,
            "session_cookies": session.cookies.get_dict(),
        }

        if response.get("status") == "success":
            response["order_form_id"] = order_form_id
            response["checkout_link"] = self.build_checkout_link(order_form_id)

            # Salvar orderFormId nos contact fields para uso em ações subsequentes
            save_result = self.save_contact_fields(
                context,
                {
                    "orderFormId": order_form_id,
                    "order_form_id": order_form_id,
                },
            )
            response["contact_field_save"] = save_result

        return TextResponse(data=response)

    def add_item(
        self,
        order_form_id: str,
        sku_id: str,
        quantity,
        checkout_order_form_ownership: str,
        checkout_vtex_cookie: str,
    ) -> TextResponse:
        if not order_form_id:
            return TextResponse(
                data={"error": "orderFormId é obrigatório para adicionar itens ao carrinho."}
            )
        if not sku_id:
            return TextResponse(
                data={"error": "skuId é obrigatório para adicionar itens ao carrinho."}
            )

        quantity_value = 1
        try:
            quantity_value = int(quantity)
        except (TypeError, ValueError):
            quantity_value = 1

        normalized_sku = self.normalize_sku(str(sku_id))

        payload = {
            "orderItems": [
                {
                    "quantity": quantity_value,
                    "seller": "1",
                    "id": normalized_sku,
                }
            ]
        }

        headers = {"Content-Type": "application/json"}
        cookie_header = self.build_cookie_header(
            checkout_order_form_ownership=checkout_order_form_ownership,
            checkout_vtex_cookie=checkout_vtex_cookie,
        )
        if cookie_header:
            headers["Cookie"] = cookie_header

        url = self.ADD_ITEM_URL.format(order_form_id=order_form_id)
        response = self.perform_request("POST", url, headers=headers, json_data=payload)
        if response.get("status") == "success":
            response["checkout_link"] = self.build_checkout_link(order_form_id)
        return TextResponse(data=response)

    def update_items(
        self,
        order_form_id: str,
        order_items_raw,
        checkout_vtex_cookie: str,
    ) -> TextResponse:
        if not order_form_id:
            return TextResponse(
                data={"error": "orderFormId é obrigatório para atualizar itens do carrinho."}
            )

        order_items = self.parse_items(order_items_raw)
        if not order_items:
            return TextResponse(
                data={
                    "error": "order_items é obrigatório e deve conter uma lista de objetos com quantity e index ou ids de SKUs.",
                    "expected": [
                        {"id": "123456", "quantity": 2},
                        {"index": 0, "quantity": 2}
                    ],
                }
            )

        normalized_items = []
        for item in order_items:
            if isinstance(item, dict):
                item_copy = dict(item)
                if "id" in item_copy:
                    item_copy["id"] = self.normalize_sku(item_copy["id"])
                if "sku" in item_copy and "id" not in item_copy:
                    item_copy["id"] = self.normalize_sku(item_copy.pop("sku"))
                if "qty" in item_copy and "quantity" not in item_copy:
                    item_copy["quantity"] = int(item_copy.pop("qty")) if str(item_copy.get("qty")).isdigit() else item_copy.get("qty")
                normalized_items.append(item_copy)
            elif isinstance(item, (str, int)):
                normalized_items.append(
                    {
                        "id": self.normalize_sku(str(item)),
                        "quantity": 1,
                        "seller": "1",
                    }
                )
            else:
                normalized_items.append(item)

        payload = {"orderItems": normalized_items}
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if checkout_vtex_cookie:
            headers["Cookie"] = self.build_cookie_header(
                checkout_vtex_cookie=checkout_vtex_cookie
            )

        url = self.UPDATE_ITEMS_URL.format(order_form_id=order_form_id)
        response = self.perform_request("POST", url, headers=headers, json_data=payload)
        if response.get("status") == "success":
            response["checkout_link"] = self.build_checkout_link(order_form_id)
        return TextResponse(data=response)

    def remove_all_items(
        self,
        order_form_id: str,
        checkout_order_form_ownership: str,
        checkout_vtex_cookie: str,
    ) -> TextResponse:
        if not order_form_id:
            return TextResponse(
                data={"error": "orderFormId é obrigatório para remover todos os itens."}
            )

        headers = {"Content-Type": "application/json"}
        cookie_header = self.build_cookie_header(
            checkout_order_form_ownership=checkout_order_form_ownership,
            checkout_vtex_cookie=checkout_vtex_cookie,
        )
        if cookie_header:
            headers["Cookie"] = cookie_header

        url = self.REMOVE_ALL_URL.format(order_form_id=order_form_id)
        response = self.perform_request("POST", url, headers=headers, raw_data="")
        if response.get("status") == "success":
            response["checkout_link"] = self.build_checkout_link(order_form_id)
        return TextResponse(data=response)
