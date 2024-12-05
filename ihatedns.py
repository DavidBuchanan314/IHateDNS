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

RECORDS = {
	("example.com", "A"): ["1.2.3.4"],
	("reddit.com", "AAAA"): ["::1"],
	("_atproto.bob.test", "TXT"): ["did=did:plc:blah"]
}

def stringify_rrset(rrset: dns.rrset.RRset):
	return (
		rrset.name.to_text(True),
		dns.rdatatype.to_text(rrset.rdtype),
		[str(rdata) for rdata in rrset.to_rdataset().items.keys()]
	)

def answer_question(question: dns.rrset.RRset) -> dns.rrset.RRset:
	if question.rdclass != dns.rdataclass.IN:
		raise ValueError("unsupported rdclass")
	name = question.name.to_text(True)
	rdtype = dns.rdatatype.to_text(question.rdtype)
	answer_text = RECORDS[(name, rdtype)]
	print(f"resolved {name} {rdtype} -> {answer_text}")
	return dns.rrset.from_text(
		question.name,
		60, # ttl
		question.rdclass,
		question.rdtype,
		*answer_text
	)

def handle_dns_query(query: dns.message.Message) -> dns.message.Message:
	response = dns.message.make_response(query)
	try:
		response.answer = [answer_question(q) for q in query.question]
	except KeyError:
		response.set_rcode(dns.rcode.NXDOMAIN)
	except:
		response.set_rcode(dns.rcode.SERVFAIL)
	return response

class DNSUDPProtocol(asyncio.DatagramProtocol):
	def connection_made(self, transport):
		self.transport = transport

	def datagram_received(self, data, addr):
		query = dns.message.from_wire(data)
		response = handle_dns_query(query)
		self.transport.sendto(response.to_wire(), addr) # NOTE: does not handle too-long responses



routes = web.RouteTableDef()

@routes.put("/{name}/{rdtype}/{rdata}") # TODO: consider supporting passing rdclass and ttl?
async def put_record(request: web.Request):
	parts = request.match_info
	try:
		rrset = dns.rrset.from_text(
			parts["name"],
			60,
			"IN",
			parts["rdtype"],
			parts["rdata"] # TODO: support multiple rdatas?
		)
	except dns.exception.SyntaxError as e:
		return web.HTTPBadRequest(text=f"{e}\n")
	print(rrset)
	name, rdtype, rdata = stringify_rrset(rrset)
	RECORDS[(name, rdtype)] = rdata
	return web.Response()


async def main():
	loop = asyncio.get_running_loop()

	# start the DNS UDP server
	transport, _ = await loop.create_datagram_endpoint(
		DNSUDPProtocol, ("127.0.0.1", 5337)
	)

	# set up the HTTP server
	app = web.Application()
	app.add_routes(routes)
	runner = web.AppRunner(app)
	await runner.setup()
	site = web.TCPSite(runner, host="127.0.0.1", port=8053)
	await site.start()

	try:
		while True:
			await asyncio.sleep(3600) # sleep forever
	finally:
		transport.close() # close the DNS server


if __name__ == "__main__":
	import argparse
	parser = argparse.ArgumentParser(
		description="The DNS server for those who hate DNS"
	)
	args = parser.parse_args()
	print(args)
	asyncio.run(main())
