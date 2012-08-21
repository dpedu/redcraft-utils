#!/usr/bin/env python
import sys

if len(sys.argv)<3 or sys.argv[1] not in ['account', 'accounts', 'ip']:
	print """Usage:
./ipchecker.py [mode] [data]
./ipchecker.py account playername
./ipchecker.py accounts playername
./ipchecker.py ip playername
"""
	sys.exit(0);

ips = {}
bytes = 0
byteslastshown = 0

f = open("server.log", "r")
while True:
	line = f.readline()
	if line == "":
		break;
	
	bytes += len(line)
	
	if bytes - byteslastshown > 1024*1024*10:
		print "Read %sM" % int(bytes/1024/1024)
		byteslastshown = bytes
		
	if "] logged in with entity id " in line:
		line = line.split("[/")
		lineAccount = line[0].split(" ")
		account = lineAccount[-1].lower()
		ip = line[1].split(":")[0]
		if not ip in ips:
			ips[ip]=[]
		if not account in ips[ip]:
			ips[ip].append(account)
f.close()

print "--------\n\n"

mode = sys.argv[1]
param = sys.argv[2].lower()

if mode == "account" or mode == "accounts":
	for ip in ips:
		for account in ips[ip]:
			if mode=="account" and account == param:
				print ip
			if mode=="accounts":
				if account == param:
					print ip
					for localaccounts in ips[ip]:
						if localaccounts == param:
							arrow = "      <-------"
						else:
							arrow = ""
						print "\t%s%s" % (localaccounts, arrow)
elif mode == "ip":
	if param in ips:
		print param
		for account in ips[param]:
			print "\t%s" % account
