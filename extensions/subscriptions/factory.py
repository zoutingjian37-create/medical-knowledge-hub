"""Construct the production subscription runner from existing small adapters."""

from extensions.platforms.wechat.discovery import WeChatUIDiscoverer
from extensions.platforms.wechat.parser import OpenCLIWeChatParser
from extensions.processing.compiler import KnowledgeCompiler
from extensions.processing.job_queue import KnowledgeJobQueue

from .discovery import DefaultLiteratureDiscoverer
from .fulltext import FullTextResolverChain
from .pipeline import LiteraturePipeline
from .runner import SubscriptionRunner, WeChatSubscriptionPipeline
from .runs import LiteratureRunStore
from .store import SubscriptionStore
from .zotero import ZoteroGateway


def build_subscription_runner() -> SubscriptionRunner:
    store = SubscriptionStore()
    runs = LiteratureRunStore(store.root)
    queue = KnowledgeJobQueue()
    compiler = KnowledgeCompiler()
    fulltext = FullTextResolverChain()
    literature = LiteraturePipeline(
        discoverer=DefaultLiteratureDiscoverer(fulltext=fulltext),
        zotero=ZoteroGateway(fulltext=fulltext),
        queue=queue,
        compiler=compiler,
        run_store=runs,
        subscription_store=store,
        state_root=store.root,
    )
    wechat = WeChatSubscriptionPipeline(
        discoverer=WeChatUIDiscoverer(),
        parser=OpenCLIWeChatParser(),
        queue=queue,
        compiler=compiler,
        run_store=runs,
    )
    return SubscriptionRunner(
        store=store,
        literature_pipeline=literature,
        wechat_pipeline=wechat,
    )
