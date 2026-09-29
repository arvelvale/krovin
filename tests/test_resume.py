import json
from agent import resume
from agent.kernel import Agent
from conftest import reply
from test_kernel import pick, make_agent


def test_resume_checkpoint_and_interrupted_batch(cfg, monkeypatch):
    agent, _ = make_agent(cfg, monkeypatch, [], decision=pick(None))
    agent.trace.turn = 2
    agent.trace.emit('turn.start', {'input':'original'})
    agent.conv.add({'role':'user','content':'原始目标'},2)
    agent.working.update(goal='实现番茄钟',todo=[{'item':'测试','done':False}])
    resume.save(agent)
    assistant=reply(calls=[('read_file',{'path':'README.md'}),('write_file',{'path':'x','content':'x'})]).assistant_message()
    agent.conv.add(assistant,2)
    agent.conv.add({'role':'tool','tool_call_id':assistant['tool_calls'][0]['id'],'content':'已读取'},2)
    cfg2=cfg
    recovered=Agent(cfg2,session=agent.session,decision=pick(None),clients=agent.clients)
    assert recovered.working.goal=='实现番茄钟'
    assert recovered.trace.turn==2 and recovered.trace._seq==agent.trace._seq
    results=[m for m in recovered.conv.messages if m['role']=='tool']
    assert len(results)==2 and results[0]['content']=='已读取'
    assert '是否已生效未知' in results[1]['content']
    assert not (cfg.workspace/'x').exists()
    seq=recovered.conv._seq
    recovered.conv.add({'role':'user','content':'继续'},3)
    assert recovered.conv._seq==seq+1
    recovered.trace.emit('turn.start',{'input':'继续'})
    records=resume.records(recovered.trace.path)
    assert len({e['seq'] for e in records})==len(records)


def test_checkpoint_keeps_compressed_context(cfg, monkeypatch):
    agent,_=make_agent(cfg,monkeypatch,[],decision=pick(None))
    agent.conv.add({'role':'user','content':'旧消息'},1)
    agent.conv.messages=[]; agent.conv.turns=[]
    agent.conv.summaries=[{'id':'sum1','turn':1,'text':'旧消息摘要'}]
    resume.save(agent)
    recovered=Agent(cfg,session=agent.session,decision=pick(None),clients=agent.clients)
    assert not recovered.conv.messages
    assert recovered.conv.summaries[0]['text']=='旧消息摘要'

def test_restore_repairs_torn_jsonl_tail(cfg, monkeypatch):
    agent,_=make_agent(cfg,monkeypatch,[],decision=pick(None))
    agent.conv.add({'role':'user','content':'完整记录'},1)
    with agent.archive.path.open('ab') as f:
        f.write(b'{"kind":')
    recovered=Agent(cfg,session=agent.session,decision=pick(None),clients=agent.clients)
    recovered.conv.add({'role':'user','content':'恢复后记录'},2)
    data=[json.loads(line) for line in agent.archive.path.read_text(encoding='utf-8').splitlines()]
    assert len(data)==2
