from typing import Optional, Tuple
import argparse
import logging
import dns
import dns.message
import dns.flags
import dns.opcode
import dns.query
import dns.rdata
import dns.rrset
import dns.rcode
import dns.resolver
import dns.rdataclass
import dns.rdatatype
import dns.exception
import dns.ipv4
import asyncio
import sqlite3
from aiohttp import web

RDATA_SEP = "," # if you want to store TXT records with commas in, you probably want to change this
DEFAULT_TTL = 60

logger = logging.getLogger(__name__)

def row_to_rrset(row: tuple) -> dns.rrset.RRset:
	name, ttl, rdclass, rdtype, rdatas = row
	return dns.rrset.from_text(name, ttl, rdclass, rdtype, *rdatas.split(RDATA_SEP))

def rrset_to_row(rrset: dns.rrset.RRset) -> Tuple[str, int, str, str, str]:
	return (
		rrset.name.to_text(),
		rrset.ttl,
		dns.rdataclass.to_text(rrset.rdclass),
		dns.rdatatype.to_text(rrset.rdtype),
		RDATA_SEP.join(map(str, rrset.to_rdataset().items.keys()))
	)

def query_db(db: sqlite3.Connection, name: str, rdclass: str, rdtype: str) -> Optional[dns.rrset.RRset]:
	row = db.execute(
		"""
			SELECT name, ttl, rdclass, rdtype, rdatas
			FROM record WHERE name=? AND rdclass=? AND rdtype=?
		""",
		(name.lower(), rdclass.upper(), rdtype.upper())
	).fetchone()
	if row is None:
		return None
	return row_to_rrset(row)

def absolutify(name: str) -> str:
	if name.endswith("."):
		return name
	return name + "."

def answer_question(db: sqlite3.Connection, question: dns.rrset.RRset) -> dns.rrset.RRset:
	name = question.name.to_text()
	rdclass = dns.rdataclass.to_text(question.rdclass)
	rdtype = dns.rdatatype.to_text(question.rdtype)
	rrset = query_db(db, name, rdclass, rdtype)
	if rrset is None:
		raise KeyError()
	return rrset

def handle_dns_query(db: sqlite3.Connection, query: dns.message.Message) -> dns.message.Message:
	logger.info(f"Question: {query.question}")
	response = dns.message.make_response(query)
	try:
		response.answer = [answer_question(db, q) for q in query.question]
	except KeyError:
		response.set_rcode(dns.rcode.NXDOMAIN)
	except:
		response.set_rcode(dns.rcode.SERVFAIL)
	logger.info(f"Answer:   {response.answer}")
	return response

class DNSProtocolUDP(asyncio.DatagramProtocol):
	def __init__(self, db: sqlite3.Connection) -> None:
		self.db = db
		super().__init__()

	def connection_made(self, transport: asyncio.DatagramTransport) -> None:
		self.transport = transport

	def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
		query = dns.message.from_wire(data)
		logger.info(f"Received DNS query from UDP {addr[0]}")
		response = handle_dns_query(self.db, query)
		response_bytes = response.to_wire()
		if len(response_bytes) > 512:
			response.flags |= dns.flags.TC # truncated response (client should retry on TCP)
			response_bytes = response.to_wire()[:512]
		self.transport.sendto(response_bytes, addr)


async def handle_tcp_client(db: sqlite3.Connection, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
	try:
		while True:
			data_len = int.from_bytes(await reader.readexactly(2))
			data = await reader.readexactly(data_len)
			query = dns.message.from_wire(data)
			logger.info(f"Received DNS query from TCP {writer.get_extra_info('peername')[0]}")
			response = handle_dns_query(db, query)
			response_bytes = response.to_wire()
			if len(response_bytes) > 0xffff: # is this the right thing to do?
				response.flags |= dns.flags.TC
				response_bytes = response.to_wire()[:0xffff]
			writer.write(len(response_bytes).to_bytes(2) + response_bytes)
			await writer.drain()
	except asyncio.IncompleteReadError:
		pass
	finally:
		writer.close()

routes = web.RouteTableDef()

# short version for people in a hurry
@routes.put("/{name}/{rdata}") # /example.com/1.2.3.4
@routes.put("/{name}/{rdtype}/{rdata}") # example.com/A/1.2.3.4
@routes.put("/{name}/{ttl}/{rdtype}/{rdata}") # example.com/60/A/1.2.3.4
@routes.put("/{name}/{ttl}/{rdclass}/{rdtype}/{rdata}") # example.com/60/IN/A/1.2.3.4
async def put_record(request: web.Request):
	parts = request.match_info
	try:
		rrset = dns.rrset.from_text(
			absolutify(parts["name"]),
			parts.get("ttl", DEFAULT_TTL),
			parts.get("rdclass", "IN"),
			parts.get("rdtype", "A"),
			*parts["rdata"].split(RDATA_SEP)
		)
	except dns.exception.SyntaxError as e:
		return web.HTTPBadRequest(text=f"{e}\n")
	if rrset.rdtype == dns.rdatatype.ANY:
		return web.HTTPBadRequest(text=f"can't set ANY\n")
	db: sqlite3.Connection = request.app["db"]
	db.execute(
		"""
			REPLACE INTO record (name, ttl, rdclass, rdtype, rdatas)
			VALUES (?, ?, ?, ?, ?)
		""",
		rrset_to_row(rrset)
	)
	db.commit()
	return web.Response()


# a lot of noise to make the trailing slash optional...
@routes.get("/{name}")
@routes.get("/{name}/")
@routes.get("/{name}/{rdtype}")
@routes.get("/{name}/{rdtype}/")
@routes.get("/{name}/{rdclass}/{rdtype}")
@routes.get("/{name}/{rdclass}/{rdtype}/")
async def get_record(request: web.Request):
	parts = request.match_info
	db: sqlite3.Connection = request.app["db"]
	rrset = query_db(db,
		absolutify(parts["name"]),
		parts.get("rdclass", "IN"),
		parts.get("rdtype", "A")
	)
	if rrset is None:
		return web.HTTPNotFound(text="NXDOMAIN\n")
	return web.Response(text=f"{rrset}\n")


@routes.get("/")
async def dump_records(request: web.Request):
	db: sqlite3.Connection = request.app["db"]
	res = web.StreamResponse()
	res.content_type = "text/plain"
	await res.prepare(request)
	for row in db.execute("SELECT name, ttl, rdclass, rdtype, rdatas FROM record"):
		await res.write(str(row_to_rrset(row)).encode() + b"\n")
	await res.write_eof()
	return res


async def async_main(db_path: str, listen_host: str, dns_port: int, http_port: int):
	loop = asyncio.get_running_loop()
	logging.basicConfig(level=logging.INFO)

	# set up the db
	logger.info(f"Persisting records to {db_path!r}")
	db = sqlite3.connect(db_path)
	db.execute("""CREATE TABLE IF NOT EXISTS record (
		name TEXT,
		ttl INTEGER,
		rdclass TEXT,
		rdtype TEXT,
		rdatas TEXT,
		PRIMARY KEY(name, rdclass, rdtype)
	)""")

	# start the UDP DNS server
	transport, _ = await loop.create_datagram_endpoint(
		lambda: DNSProtocolUDP(db), (listen_host, dns_port)
	)
	logger.info(f"DNS server listening on UDP {listen_host}:{dns_port}")

	# start the TCP DNS server
	await asyncio.start_server(
		lambda r, w: handle_tcp_client(db, r, w), # inject the db
		host=listen_host,
		port=dns_port
	)
	logger.info(f"DNS server listening on TCP {listen_host}:{dns_port}")

	# set up the HTTP server
	app = web.Application()
	app["db"] = db
	app.add_routes(routes)
	runner = web.AppRunner(app)
	await runner.setup()
	site = web.TCPSite(runner, host=listen_host, port=http_port)
	await site.start()
	logger.info(f"HTTP server listening on http://{listen_host}:{http_port}")

	try:
		while True:
			await asyncio.sleep(3600) # sleep forever
	except asyncio.CancelledError:
		logging.info("Shutting down...")
	finally:
		transport.close() # close the DNS server

def main():
	parser = argparse.ArgumentParser(
		description="The DNS server for people who hate DNS"
	)
	parser.add_argument("--db", default=":memory:", help="sqlite3 db path for persisting records (defaults to :memory: i.e. no persistence)")
	parser.add_argument("--host", default="127.0.0.1", help="listen host (default '127.0.0.1')")
	parser.add_argument("--dns-port", type=int, default=5337, help="default 5337 (UDP)")
	parser.add_argument("--http-port", type=int, default=8053, help="default 8053")
	args = parser.parse_args()
	asyncio.run(async_main(args.db, args.host, args.dns_port, args.http_port))

if __name__ == "__main__":
	main()
