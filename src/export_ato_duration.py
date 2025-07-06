# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

import csv
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from io import StringIO
from json import loads
import logging
from typing import Dict, List

@dataclass
class FedRAMPProduct:
  id: str
  name: str
  csp: str
  cso: str
  logo: str
  service_offering: str
  status: str
  authorization: int
  reuse: int
  ready_status: str
  ready_date: str
  ip_jab_status: str
  ip_jab_date: str
  ip_prog_status: str
  ip_prog_date: str
  ip_prog_date2: str
  ip_agency_status: str
  ip_agency_date: str
  ip_pmo_status: str
  ip_pmo_date: str
  auth_date: str
  auth_type: str
  fedramp_ready: str
  partnering_agency: str
  fedramp_auth: str
  annual_assessment: str
  independent_assessor: str
  service_model: List[str]
  deployment_model: str
  impact_level: str
  impact_level_number: str
  leveraged_systems: List[str]
  agency_authorizations: List[str]
  agency_reuse: List[str]
  service_desc: str
  fedramp_msg: str
  sales_email: str
  security_email: str
  website: str
  uei: str
  small_business: str
  business_function: List[str]
  service_last_90: List[str]
  all_others: List[str]
  filter_classes: str

@dataclass
class FedRAMPAuthorization:
  id: str
  csp: str
  cso: str
  duration: int = -1
  reuse: int = 0

def get_products(data: StringIO) -> List[FedRAMPProduct]:
  """Deserialize data from buffer or path load into Python dictionary.
  """
  raw_data: Dict[str, any] = loads(data)
  product_data = raw_data.get("data", {}).get("Products", [])
  return [
    FedRAMPProduct(**pd)
    for pd in product_data
  ]

def main() -> None:
  durations: int = 0
  authorizations: List[FedRAMPAuthorization] = []
  with (open("data/gsa/marketplace-fedramp-gov-data/data.json") as input_fd,
        open("data/fedramp_ato_durations.csv", "w", newline="") as output_fd):
    csv_field_names = [field.name for field in fields(FedRAMPAuthorization)]    
    csv_writer = csv.DictWriter(output_fd, fieldnames=csv_field_names)
    csv_writer.writeheader()
    products: List[FedRAMPProduct] = get_products(input_fd.read())
    for product in products:
      if product.ready_date != "No FRR Date":
        start_dt = datetime.fromisoformat(product.ready_date)
      elif product.ip_jab_date != "Not Active":
        start_dt = datetime.fromisoformat(product.ip_jab_date)
      elif product.ip_agency_date != "Not Active":
        start_dt = datetime.fromisoformat(product.ip_agency_date)
      else:
        logging.error(f"no computable start date for {product.id}, skipping")
        continue
      try:
        end_dt = datetime.fromisoformat(product.fedramp_auth)
      except ValueError:
        end_dt = datetime.now(timezone.utc)
      duration=end_dt-start_dt
      authorization = FedRAMPAuthorization(
        id=product.id,
        csp=product.csp,
        cso=product.cso,
        reuse=product.reuse,
        duration=duration.days
      )
      authorizations.append(authorization)
      csv_writer.writerow(asdict(authorization))
  durations = [ato.duration for ato in authorizations]
  durations_average = sum(durations)/len(durations)
  print(f"average duration for history of FedRAMP authorizations is {durations_average}")

if __name__ == "__main__":
  main()