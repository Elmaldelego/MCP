import httpx
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from models import FDARecall, CAERSEvent

logger = logging.getLogger("vigia.openfda")

class OpenFDAClient:
    """
    Cliente para la API de openFDA.
    Soporta:
    - Food Enforcement (Recalls)
    - Food Adverse Events (CAERS)
    """

    RECALL_URL = "https://api.fda.gov/food/enforcement.json"
    EVENT_URL  = "https://api.fda.gov/food/event.json"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.timeout = 20.0

    def _get_date_5_years_ago(self) -> str:
        """Retorna la fecha de hace 5 años en formato YYYYMMDD."""
        date = datetime.now() - timedelta(days=5*365)
        return date.strftime("%Y%m%d")

    async def fetch_recalls(
        self, 
        product_name: str, 
        hazard_types: List[str] = None, 
        limit: int = 10,
        years: int = 5
    ) -> List[FDARecall]:
        """Busca retiros en openFDA (Food Enforcement)."""
        search_terms = []
        
        if product_name:
            search_terms.append(f'product_description:"{product_name}"')

        if hazard_types:
            hazards_query = " OR ".join([f'reason_for_recall:"{h}"' for h in hazard_types])
            search_terms.append(f"({hazards_query})")

        # Filtro de fecha
        start_date = (datetime.now() - timedelta(days=years*365)).strftime("%Y%m%d")
        search_terms.append(f"report_date:[{start_date} TO {datetime.now().strftime('%Y%m%d')}]")

        query = " AND ".join(search_terms)
        params = {"search": query, "limit": limit, "sort": "report_date:desc"}
        if self.api_key: params["api_key"] = self.api_key

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.info(f"Consultando Recalls con query: {query}")
                response = await client.get(self.RECALL_URL, params=params)
                if response.status_code == 404: return []
                response.raise_for_status()
                results = response.json().get("results", [])
                return [
                    FDARecall(
                        recall_number      = r.get("recall_number", "N/A"),
                        product_description = r.get("product_description", "N/A"),
                        reason_for_recall  = r.get("reason_for_recall", "N/A"),
                        recalling_firm     = r.get("recalling_firm", "N/A"),
                        recall_initiation_date = r.get("recall_initiation_date", "N/A"),
                        classification     = r.get("classification", "N/A"),
                        status             = r.get("status", "N/A"),
                    )
                    for r in results
                ]
        except Exception as exc:
            logger.error(f"Error en fetch_recalls: {exc}")
            return []

    async def fetch_adverse_events(
        self,
        product_name: str,
        limit: int = 10,
        years: int = 5
    ) -> List[CAERSEvent]:
        """Busca eventos adversos en openFDA (CAERS)."""
        search_terms = []
        if product_name:
            # Buscamos en el nombre de marca del producto
            search_terms.append(f'products.name_brand:"{product_name}"')

        start_date = (datetime.now() - timedelta(days=years*365)).strftime("%Y%m%d")
        search_terms.append(f"date_created:[{start_date} TO {datetime.now().strftime('%Y%m%d')}]")

        query = " AND ".join(search_terms)
        params = {"search": query, "limit": limit, "sort": "date_created:desc"}
        if self.api_key: params["api_key"] = self.api_key

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.info(f"Consultando CAERS con query: {query}")
                response = await client.get(self.EVENT_URL, params=params)
                if response.status_code == 404: return []
                response.raise_for_status()
                results = response.json().get("results", [])
                
                events = []
                for r in results:
                    products = r.get("products", [])
                    events.append(CAERSEvent(
                        report_number = r.get("report_number", "N/A"),
                        date_created  = r.get("date_created", "N/A"),
                        outcomes      = r.get("outcomes", []),
                        reactions     = r.get("reactions", []),
                        product_names = [p.get("name_brand", "N/A") for p in products],
                        industry_name = products[0].get("industry_name") if products else None
                    ))
                return events
        except Exception as exc:
            logger.error(f"Error en fetch_adverse_events: {exc}")
            return []

    async def fetch_all(self, product_name: str, hazard_types: List[str] = None, limit_per_query: int = 10) -> List[FDARecall]:
        """Alias para mantener compatibilidad con server.py actual."""
        return await self.fetch_recalls(product_name, hazard_types, limit=limit_per_query)
