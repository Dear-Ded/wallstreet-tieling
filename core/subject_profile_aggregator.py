#!/usr/bin/env python3
"""SubjectProfileAggregator — 主程序画像聚合引擎

v0.5.0 新增模块。从多个数据源聚合主程序信息，输出结构化主程序画像报告。

数据源适配器（统一接口）：
- IdentityAdapter: 身份信息
- ContactAdapter: 联系方式
- AddressAdapter: 地址信息
- TravelAdapter: 出行记录
- ConsumptionAdapter: 消费/行为记录
- SocialAdapter: 社交关系

架构：模块化、并发查询、TTL缓存、深度关联（默认3层）、结构化输出。
"""
from __future__ import annotations
import asyncio,hashlib,json,logging,time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

@dataclass
class AdapterResult:
    source: str; subject_id: str; status: str = "empty"
    data: dict[str,Any] = field(default_factory=dict); error_message: str = ""
    retrieved_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    confidence: float = 0.5; source_url: str = ""

@dataclass
class SubjectEntity:
    entity_id: str; name: str; entity_type: str = "company"
    attributes: dict[str,Any] = field(default_factory=dict); relation_to_seed: str = ""; depth: int = 0

@dataclass
class SubjectProfileReport:
    seed_subject_id: str; seed_subject_name: str
    generated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    identity: dict[str,Any] = field(default_factory=dict); contacts: dict[str,Any] = field(default_factory=dict)
    addresses: dict[str,Any] = field(default_factory=dict); travel_records: list = field(default_factory=list)
    consumption_records: list = field(default_factory=list); social_relations: dict[str,Any] = field(default_factory=dict)
    related_entities: list = field(default_factory=list); relation_graph: dict[str,list] = field(default_factory=dict)
    source_count: int = 0; failed_sources: list = field(default_factory=list)
    empty_sources: list = field(default_factory=list); cache_hit_count: int = 0; query_depth: int = 3
    def to_dict(self) -> dict:
        return {
            "seed_subject_id":self.seed_subject_id,"seed_subject_name":self.seed_subject_name,
            "generated_at":self.generated_at,"identity":self.identity,"contacts":self.contacts,
            "addresses":self.addresses,"travel_records":self.travel_records,
            "consumption_records":self.consumption_records,"social_relations":self.social_relations,
            "related_entities":[{"entity_id":e.entity_id,"name":e.name,"entity_type":e.entity_type,
            "attributes":e.attributes,"relation_to_seed":e.relation_to_seed,"depth":e.depth} for e in self.related_entities],
            "relation_graph":self.relation_graph,"source_count":self.source_count,
            "failed_sources":self.failed_sources,"empty_sources":self.empty_sources,
            "cache_hit_count":self.cache_hit_count,"query_depth":self.query_depth,
        }

class BaseAdapter(ABC):
    def __init__(self,name:str,timeout_seconds:float=8.0): self.name=name; self.timeout=timeout_seconds
    @abstractmethod
    async def fetch(self,subject_id:str,params:dict|None=None) -> AdapterResult: ...
    def cache_key(self,subject_id:str,params:dict|None=None) -> str:
        return hashlib.sha256(f"{self.name}:{subject_id}:{json.dumps(params or {},sort_keys=True)}".encode()).hexdigest()[:32]

class IdentityAdapter(BaseAdapter):
    def __init__(self,resolver:Callable|None=None,**kwargs):
        super().__init__("identity_adapter",**kwargs); self._resolver=resolver
    async def fetch(self,subject_id,params=None) -> AdapterResult:
        try: return await asyncio.wait_for(self._do_fetch(subject_id,params),timeout=self.timeout)
        except asyncio.TimeoutError: return AdapterResult(source=self.name,subject_id=subject_id,status="timeout")
        except Exception as e: return AdapterResult(source=self.name,subject_id=subject_id,status="error",error_message=str(e))
    async def _do_fetch(self,subject_id,params=None) -> AdapterResult:
        raw = await self._resolver(subject_id) if self._resolver and asyncio.iscoroutinefunction(self._resolver) else (self._resolver(subject_id) if self._resolver else {})
        data = {"name":raw.get("name",subject_id),"aliases":raw.get("aliases",[]),
            "identifiers":{"unified_social_credit_code":raw.get("uscc"),"business_registration_number":raw.get("reg_no"),"lei":raw.get("lei"),"cik":raw.get("cik")},
            "entity_type":raw.get("entity_type","company"),"brands":raw.get("brands",[])}
        return AdapterResult(source=self.name,subject_id=subject_id,status="success",data=data,confidence=0.85)

class ContactAdapter(BaseAdapter):
    def __init__(self,resolver=None,**kwargs): super().__init__("contact_adapter",**kwargs); self._resolver=resolver
    async def fetch(self,subject_id,params=None) -> AdapterResult:
        try: return await asyncio.wait_for(self._do_fetch(subject_id,params),timeout=self.timeout)
        except asyncio.TimeoutError: return AdapterResult(source=self.name,subject_id=subject_id,status="timeout")
        except Exception as e: return AdapterResult(source=self.name,subject_id=subject_id,status="error",error_message=str(e))
    async def _do_fetch(self,subject_id,params=None) -> AdapterResult:
        raw = await self._resolver(subject_id) if self._resolver and asyncio.iscoroutinefunction(self._resolver) else (self._resolver(subject_id) if self._resolver else {})
        data = {"phones":raw.get("phones",[]),"emails":raw.get("emails",[]),"domains":raw.get("domains",[])}
        return AdapterResult(source=self.name,subject_id=subject_id,status="success" if any(data.values()) else "empty",data=data)

class AddressAdapter(BaseAdapter):
    def __init__(self,resolver=None,**kwargs): super().__init__("address_adapter",**kwargs); self._resolver=resolver
    async def fetch(self,subject_id,params=None) -> AdapterResult:
        try: return await asyncio.wait_for(self._do_fetch(subject_id,params),timeout=self.timeout)
        except asyncio.TimeoutError: return AdapterResult(source=self.name,subject_id=subject_id,status="timeout")
        except Exception as e: return AdapterResult(source=self.name,subject_id=subject_id,status="error",error_message=str(e))
    async def _do_fetch(self,subject_id,params=None) -> AdapterResult:
        raw = await self._resolver(subject_id) if self._resolver and asyncio.iscoroutinefunction(self._resolver) else (self._resolver(subject_id) if self._resolver else {})
        data = {"registered_address":raw.get("registered_address",""),"office_addresses":raw.get("office_addresses",[])}
        return AdapterResult(source=self.name,subject_id=subject_id,status="success" if data["registered_address"] else "empty",data=data)

class TravelAdapter(BaseAdapter):
    def __init__(self,resolver=None,**kwargs): super().__init__("travel_adapter",**kwargs); self._resolver=resolver
    async def fetch(self,subject_id,params=None) -> AdapterResult:
        try: return await asyncio.wait_for(self._do_fetch(subject_id,params),timeout=self.timeout)
        except asyncio.TimeoutError: return AdapterResult(source=self.name,subject_id=subject_id,status="timeout")
        except Exception as e: return AdapterResult(source=self.name,subject_id=subject_id,status="error",error_message=str(e))
    async def _do_fetch(self,subject_id,params=None) -> AdapterResult:
        raw = await self._resolver(subject_id) if self._resolver and asyncio.iscoroutinefunction(self._resolver) else (self._resolver(subject_id) if self._resolver else {})
        records = raw.get("records",raw.get("travel_records",[]))
        data = {"records":records,"record_count":len(records)}
        return AdapterResult(source=self.name,subject_id=subject_id,status="success" if records else "empty",data=data)

class ConsumptionAdapter(BaseAdapter):
    def __init__(self,resolver=None,**kwargs): super().__init__("consumption_adapter",**kwargs); self._resolver=resolver
    async def fetch(self,subject_id,params=None) -> AdapterResult:
        try: return await asyncio.wait_for(self._do_fetch(subject_id,params),timeout=self.timeout)
        except asyncio.TimeoutError: return AdapterResult(source=self.name,subject_id=subject_id,status="timeout")
        except Exception as e: return AdapterResult(source=self.name,subject_id=subject_id,status="error",error_message=str(e))
    async def _do_fetch(self,subject_id,params=None) -> AdapterResult:
        raw = await self._resolver(subject_id) if self._resolver and asyncio.iscoroutinefunction(self._resolver) else (self._resolver(subject_id) if self._resolver else {})
        records = raw.get("records",raw.get("consumption_records",[]))
        data = {"records":records,"record_count":len(records)}
        return AdapterResult(source=self.name,subject_id=subject_id,status="success" if records else "empty",data=data)

class SocialAdapter(BaseAdapter):
    def __init__(self,resolver=None,**kwargs): super().__init__("social_adapter",**kwargs); self._resolver=resolver
    async def fetch(self,subject_id,params=None) -> AdapterResult:
        try: return await asyncio.wait_for(self._do_fetch(subject_id,params),timeout=self.timeout)
        except asyncio.TimeoutError: return AdapterResult(source=self.name,subject_id=subject_id,status="timeout")
        except Exception as e: return AdapterResult(source=self.name,subject_id=subject_id,status="error",error_message=str(e))
    async def _do_fetch(self,subject_id,params=None) -> AdapterResult:
        raw = await self._resolver(subject_id) if self._resolver and asyncio.iscoroutinefunction(self._resolver) else (self._resolver(subject_id) if self._resolver else {})
        related = raw.get("related_entities",[])
        data = {"related_entities":[{"entity_id":str(e.get("id","")),"name":str(e.get("name","")),"entity_type":str(e.get("type","company")),"relation_type":str(e.get("relation","unknown"))} for e in related],
            "relation_count":len(related),"common_addresses":raw.get("common_addresses",[]),"common_projects":raw.get("common_projects",[])}
        return AdapterResult(source=self.name,subject_id=subject_id,status="success" if related else "empty",data=data)

class SubjectProfileAggregator:
    """主程序画像聚合引擎 - 并发查询所有适配器, 递归展开关联主程序, 输出结构化画像报告."""
    def __init__(self,*,max_depth:int=3,concurrency:int=6,cache_ttl_seconds:float=300.0,
        identity_resolver=None,contact_resolver=None,address_resolver=None,
        travel_resolver=None,consumption_resolver=None,social_resolver=None):
        self.max_depth=max(1,min(max_depth,5)); self.concurrency=concurrency; self.cache_ttl=cache_ttl_seconds
        self._adapters = {
            "identity":IdentityAdapter(resolver=identity_resolver),"contact":ContactAdapter(resolver=contact_resolver),
            "address":AddressAdapter(resolver=address_resolver),"travel":TravelAdapter(resolver=travel_resolver),
            "consumption":ConsumptionAdapter(resolver=consumption_resolver),"social":SocialAdapter(resolver=social_resolver),
        }
        self._cache:dict[str,tuple[float,AdapterResult]] = {}; self._cache_hits = 0

    async def aggregate(self,subject_id:str,subject_name:str="",*,params:dict|None=None) -> SubjectProfileReport:
        report = SubjectProfileReport(seed_subject_id=subject_id,seed_subject_name=subject_name or subject_id,query_depth=self.max_depth)
        results = await self._query_all_adapters(subject_id,params)
        report.cache_hit_count = self._cache_hits
        self._merge_results(report,results)
        for name,r in results.items():
            report.source_count += 1
            if r.status=="error": report.failed_sources.append(name)
            elif r.status=="empty": report.empty_sources.append(name)
        if self.max_depth>1:
            related,graph = await self._deep_association_analysis(subject_id,report,max_depth=self.max_depth)
            report.related_entities=related; report.relation_graph=graph
        return report

    async def query_single(self,adapter_name:str,subject_id:str,params=None) -> AdapterResult:
        a = self._adapters.get(adapter_name)
        return await self._cached_fetch(a,subject_id,params) if a else AdapterResult(source=adapter_name,subject_id=subject_id,status="error",error_message=f"Unknown: {adapter_name}")

    def register_adapter(self,name:str,adapter:BaseAdapter) -> None: self._adapters[name]=adapter
    def clear_cache(self) -> None: self._cache.clear(); self._cache_hits=0

    async def _query_all_adapters(self,subject_id,params=None) -> dict:
        tasks = {n: self._cached_fetch(a,subject_id,params) for n,a in self._adapters.items()}
        gathered = await asyncio.gather(*tasks.values(),return_exceptions=True)
        return {n: AdapterResult(source=n,subject_id=subject_id,status="error",error_message=str(r)) if isinstance(r,BaseException) else r for (n,_),r in zip(tasks.items(),gathered)}

    async def _cached_fetch(self,adapter,subject_id,params=None) -> AdapterResult:
        key = adapter.cache_key(subject_id,params); now = time.time()
        if key in self._cache:
            ts,cached = self._cache[key]
            if now-ts < self.cache_ttl: self._cache_hits += 1; return cached
        result = await adapter.fetch(subject_id,params)
        self._cache[key] = (now,result)
        return result

    def _merge_results(self,report,results):
        for n,r in results.items():
            if r.status not in ("success","empty"): continue
            d = r.data
            if n=="identity": report.identity.update(d)
            elif n=="contact": report.contacts.update(d)
            elif n=="address": report.addresses.update(d)
            elif n=="travel": report.travel_records = d.get("records",[])
            elif n=="consumption": report.consumption_records = d.get("records",[])
            elif n=="social": report.social_relations.update(d)

    async def _deep_association_analysis(self,subject_id,report,*,max_depth,visited=None,current_depth=0):
        if visited is None: visited=set()
        if current_depth >= max_depth: return [],[]
        visited.add(subject_id); entities=[]; graph={}
        for raw in report.social_relations.get("related_entities",[]):
            eid = str(raw.get("entity_id",""))
            if not eid or eid in visited: continue
            entity = SubjectEntity(entity_id=eid,name=str(raw.get("name",eid)),entity_type=str(raw.get("entity_type","company")),relation_to_seed=str(raw.get("relation_type","unknown")),depth=current_depth+1)
            entities.append(entity); graph.setdefault(subject_id,[]).append(eid)
        return entities,graph
