from typing import Tuple, Optional
import dns # dnspython
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

RDATA_SEP = ","
DEFAULT_TTL = 60

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
	name, ttl, rdclass, rdtype, rdatas = row
	return dns.rrset.from_text(name, ttl, rdclass, rdtype, *rdatas.split(RDATA_SEP))

def insert_db(db: sqlite3.Connection, rrset: dns.rrset.RRset) -> None:
	db.execute(
		"""
			REPLACE INTO record (name, ttl, rdclass, rdtype, rdatas)
			VALUES (?, ?, ?, ?, ?)
		""",(
			rrset.name.to_text(),
			rrset.ttl,
			dns.rdataclass.to_text(rrset.rdclass),
			dns.rdatatype.to_text(rrset.rdtype),
			RDATA_SEP.join(map(str, rrset.to_rdataset().items.keys()))
		)
	)

def absolutify(name: str) -> str:
	if name.endswith("."):
		return name
	return name + "."

def answer_question(db: sqlite3.Connection, question: dns.rrset.RRset) -> dns.rrset.RRset:
	name = question.name.to_text()
	rdclass = dns.rdataclass.to_text(question.rdclass)
	rdtype = dns.rdatatype.to_text(question.rdtype)
	rrset = query_db(db, name, rdclass, rdtype)
	print("answering")
	print(rrset)
	if rrset is None:
		raise KeyError()
	return rrset

def handle_dns_query(db: sqlite3.Connection, query: dns.message.Message) -> dns.message.Message:
	response = dns.message.make_response(query)
	try:
		response.answer = [answer_question(db, q) for q in query.question]
	except KeyError:
		response.set_rcode(dns.rcode.NXDOMAIN)
	except:
		response.set_rcode(dns.rcode.SERVFAIL)
	return response

class DNSUDPProtocol(asyncio.DatagramProtocol):
	def __init__(self, db: sqlite3.Connection) -> None:
		self.db = db
		super().__init__()

	def connection_made(self, transport):
		self.transport = transport

	def datagram_received(self, data, addr):
		query = dns.message.from_wire(data)
		response = handle_dns_query(self.db, query)
		self.transport.sendto(response.to_wire(), addr) # TODO: handle too-long responses



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
	print(rrset)
	db: sqlite3.Connection = request.app["db"]
	insert_db(db, rrset)
	return web.Response()


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

async def main():
	loop = asyncio.get_running_loop()

	# set up the db
	db = sqlite3.connect(":memory:")
	db.execute("""CREATE TABLE IF NOT EXISTS record (
		name TEXT,
		rdclass TEXT,
		rdtype TEXT,
		ttl INTEGER,
		rdatas TEXT
	)""")
	db.execute("CREATE UNIQUE INDEX IF NOT EXISTS lookup ON record (name, rdclass, rdtype)")

	# start the DNS UDP server
	transport, _ = await loop.create_datagram_endpoint(
		lambda: DNSUDPProtocol(db), ("127.0.0.1", 5337)
	)

	# set up the HTTP server
	app = web.Application()
	app["db"] = db
	app.add_routes(routes)
	runner = web.AppRunner(app)
	await runner.setup()
	site = web.TCPSite(runner, host="127.0.0.1", port=8053)
	await site.start()

	try:
		while True:
			await asyncio.sleep(3600) # sleep forever
	except asyncio.CancelledError:
		print("\nShutting down...")
	finally:
		transport.close() # close the DNS server


if __name__ == "__main__":
	import argparse
	parser = argparse.ArgumentParser(
		description="The DNS server for those who hate DNS"
	)
	parser.add_argument()
	args = parser.parse_args()
	print(args)
	asyncio.run(main())
