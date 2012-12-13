#!/usr/bin/env python
import subprocess
import os
import re
import sys
import threading
import time
import sched
import random
import re
import yaml
import traceback
import signal

class MinecraftServerRunner(threading.Thread):
	def __init__(self, configFile):
		threading.Thread.__init__(self)
		
		# Stored name of the config file
		self.configFile = configFile
		# Load config
		self.reloadConfig()
		
		# Holds the reference to the running server
		self.server = None
		# As long as this is true the server will be respawned if it dies/stops
		self.respawn = True
		
	def run(self):
		# Handler for console input
		self.stdinThread = StdinThread(self)
		
		self.timers = {
			# Countdown to restarts
			"RestartTimer":			None,
			# Warning for restarts
			"RestartWarningTimer":  None,
			# Rolling messages interval
			"MessageTimer":			threading.Timer(self.config["message_interval"], self.timer_Message),
			# Save interval
			"SaveTimer":			threading.Timer(self.config["save_interval"], self.timer_Save),
			# Check if the server needs to be respawn
			"RestartCheckTimer":	threading.Timer(1, self.timer_CheckRespawn),
			# Config relaod interval
			"ConfigReloadTimer":	threading.Timer(self.config["config_update_interval"], self.timer_ConfigReload),
		}
		# Some data
		self.data = {
			"LastMessage":0,
			"LastRestart":time.time()
		}
		# Start all the timers
		self.timers["RestartCheckTimer"].start()
		self.timers["SaveTimer"].start()
		self.timers["MessageTimer"].start()
		self.timers["ConfigReloadTimer"].start()
	
	# Called by the main thread when someone presses ctrl-c. Stops the runner
	def signal_handler(self, signal, frame):
		print " **** Ctrl-C caught - exiting runner!"
		self.doStop()
	
	# Called when RestartTimer is set off, stops the server and cancels the two relavent timers.
	def timer_Restart(self):
		self.server.stopServer()
		try:
			self.timers["RestartTimer"].cancel()
		except:
			pass
		try:
			self.timers["RestartWarningTimer"].cancel()
		except:
			pass
	
	# Called 30 seconds before the server restart, sends warning message
	def timer_RestartWarning(self):
		self.server.write("say PLANNED RESTART IN 30 SECONDS.")
		self.server.write("say ALL PROGRESS WILL BE SAVED...")
	
	# Called to display the rotating messages
	def timer_Message(self):
		self.data["LastMessage"]+=1
		if self.data["LastMessage"]>=len(self.config["messages"]):
			self.data["LastMessage"]=0
		for line in self.config["messages"][self.data["LastMessage"]]:
			self.server.write("say %s" % line)
		
		self.timers["MessageTimer"] = threading.Timer(self.config["message_interval"], self.timer_Message)
		self.timers["MessageTimer"].start()
	
	# Called to save the map
	def timer_Save(self):
		self.server.write("say MAP IS SAVING...")
		time.sleep(1.0)
		self.server.write("save-all");
		self.timers["SaveTimer"] = threading.Timer(self.config["save_interval"], self.timer_Save)
		self.timers["SaveTimer"].start()
	
	# Called to reload the config
	def timer_ConfigReload(self):
		self.reloadConfig();
		self.timers["ConfigReloadTimer"] = threading.Timer(self.config["config_update_interval"], self.timer_ConfigReload)
		self.timers["ConfigReloadTimer"].start()
	
	# Called every so often to check if the server is stopped (or nonexistant) and restarts it
	def timer_CheckRespawn(self):
		loop = True
		if self.server == None:
			self.startServer()
		else:
			if not self.server.isAlive():
				if self.respawn:
					print( "\n\n **** Respawning Server\n" )
					self.startServer()
				else:
					print( "\n\n **** Exiting\n" )
					loop = False
					sys.exit(1)
		if loop:
			self.timers["RestartCheckTimer"] = threading.Timer(1, self.timer_CheckRespawn)
			self.timers["RestartCheckTimer"].start()
	
	# Kill ALL the timers so we can shut down
	def killTimers(self):
		for timer in self.timers:
			try:
				self.timers[timer].cancel()
			except:
				pass
	
	# Reload the config from disk
	def reloadConfig(self):
		self.config = yaml.load(open(self.configFile, 'r'))
	
	# Starts a new server and sets up relavent timers
	def startServer(self):
		self.server = MinecraftServer(self)
		self.timers["RestartTimer"] = threading.Timer(self.config["restart_interval"], self.timer_Restart)
		self.timers["RestartTimer"].start()
		
		self.timers["RestartWarningTimer"] = threading.Timer(self.config["restart_interval"]-30, self.timer_RestartWarning)
		self.timers["RestartWarningTimer"].start()
	
	# Stops runner and the servers entirely
	def doStop(self):
		print( "\n\n **** Exiting Runner " )
		self.respawn = False
		self.server.stopServer()
		self.killTimers()
	
	# Processes a line from the console's STDIN
	def handleStdinLine(self, line):
		line = line.strip()
		" called for each stdin line"
		if(line.startswith("!")):
			if(line.startswith("!restart")):
				self.timers["RestartTimer"].cancel()
				self.timers["RestartWarningTimer"].cancel()
				self.timers["RestartTimer"] = threading.Timer(30, self.timer_Restart)
				self.timers["RestartTimer"].start()
				self.server.write("say PLANNED RESTART IN 30 SECONDS.")
				self.server.write("say ALL PROGRESS WILL BE SAVED...")
			elif line.startswith("!next_restart"):
				timenext = str(int((self.calcNextRestart()/60.0)*10.0)/10.0)
				print "Next restart in %s minutes." % timenext
			elif line.startswith("!trace"):
				print self.trace()
		else:
			self.server.write(line)
	
	# Handles a line from the server's stderr
	def handleServerLine(self, line):
		print( line.strip() )
		" called by the server thread whenever an output line is received "
		
		if "logged in with entity id" in line:
			newPname = line.split("[INFO] ")[1].split(" [/")[0];
		elif "[INFO] CONSOLE: Save complete." in line:
			self.server.write("say SAVE COMPLETE!");
		elif "!next_restart" in line:
			timenext = str(int((self.calcNextRestart()/60.0)*10.0)/10.0)
			self.server.write("say Next restart in %s minutes." % timenext)
	
	# Figure out how long until the next restart
	def calcNextRestart(self):
		return (self.config["restart_interval"]-(time.time()-self.data["LastRestart"]))
	
	# Print a stack trace
	def trace(self):
		result = ""
		result += "\n*** STACKTRACE - START ***\n"
		code = []
		for threadId, stack in sys._current_frames().items():
			code.append("\n# ThreadID: %s" % threadId)
			for filename, lineno, name, line in traceback.extract_stack(stack):
				code.append('File: "%s", line %d, in %s' % (filename, lineno, name))
				if line:
					code.append("  %s" % (line.strip()))
		for line in code:
			result += line + "\n"
		result += "\n*** STACKTRACE - END ***\n"
		return result

# Class representing a MC server
class MinecraftServer(threading.Thread):
	def __init__(self, master):
		threading.Thread.__init__(self)
		self.master = master
		self.server = None
		self.start()
	def run(self):
		args = (
			self.master.config["javapath"],
			"-Xms%s" % self.master.config["memory"],
			"-Xmx%s" % self.master.config["memory"],
			"-Djline.terminal=jline.UnsupportedTerminal",
			"-jar",
			self.master.config["jar"],
			"-nojline"
		)
		print( args )
		self.server = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE, preexec_fn=self.blockSig);
		
		while True:
			try:
				output = self.server.stderr.readline()
				if output == "":
					break
				handle = self.master.handleServerLine(output);
			except:
				pass
	# Block signals from hitting this thread
	def blockSig(self):
		signal.signal(signal.SIGINT, signal.SIG_IGN)
	
	# Sends text to the server
	def write(self, text):
		self.server.stdin.write(text+"\n")
	
	# Stop the server (And kick everyone)
	def stopServer(self): 
		self.write("kickall Server is restarting - Please Reconnect.");
		self.write("save-all")
		self.write("stop")
		while self.isAlive():
			time.sleep(.5)
		print( " **** Server has stopped." )
	
	# True or False if the server is alive or dead
	def isAlive(self):
		return self.server.poll() == None

# Thread for reading from STDIN
class StdinThread(threading.Thread):
	def __init__(self, master):
		threading.Thread.__init__(self)
		self.master = master
		#signal.signal(signal.SIGINT, self.master.signal_handler)
		self.start()
	def run(self):
		while self.master.respawn:
			try:
				line = sys.stdin.readline()
				if line:
					self.master.handleStdinLine(line)
				time.sleep(0.1);
			except:
				pass

if __name__ == '__main__':
	runner = MinecraftServerRunner("runner.yml")
	runner.start()
	signal.signal(signal.SIGINT, runner.signal_handler)
	
	while runner.respawn:
		time.sleep(1)
	
	# Print a trace 10 seconds after shutdown (Runner debug purposes)
	time.sleep(10)
	d = runner.trace()
	print d
