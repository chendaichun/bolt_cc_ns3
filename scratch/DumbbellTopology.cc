// This simulation implements a simple topology with 4 endpoints and 2 switches:
// C1 --- S1 --- S2 --- C3
//         |      |
//         |      |
// C2 -----+      +---- C4
//
// With RTT delays: C1-S1: 10us, C2-S1: 2us, S1-S2: 2us, S2-C3: 10us, S2-C4: 2us
// C1 sends to C3, while C2 sends to C4. Both flows compete at the S1-S2 link.

#include <stdlib.h>
#include <chrono>
#include <fstream>
#include <iostream>
#include <string>
#include <map>

#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/internet-module.h"
#include "ns3/ipv4-global-routing-helper.h"
#include "ns3/network-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/traffic-control-module.h"

using namespace ns3;

#define START_TIME 1.0
#define OUT 0

NS_LOG_COMPONENT_DEFINE("BoltSimpleDumbbellSimulation");

// Global variables to track simulation statistics
double lastDataArrivalTime;
uint64_t totalDataReceived = 0;

// Trace the congestion window sizes
void TraceFlowStats(Ptr<OutputStreamWrapper> stream, Ipv4Address saddr,
                    Ipv4Address daddr, uint16_t sport, uint16_t dport,
                    int txMsgId, uint32_t cwnd, uint64_t rtt) {
  Time now = Simulator::Now();
#if OUT
  NS_LOG_DEBUG("stats " << now.GetNanoSeconds() << " " << saddr << ":" << sport
                        << " " << daddr << ":" << dport << " " << txMsgId << " "
                        << cwnd << " " << rtt);
#endif
  *stream->GetStream() << now.GetNanoSeconds() << " " << saddr << ":" << sport
                       << " " << daddr << ":" << dport << " " << txMsgId << " "
                       << cwnd << " " << rtt << std::endl;
}

// Trace the queue lengths at switches
static void BytesInQueueDiscTrace(Ptr<OutputStreamWrapper> stream, std::string nodeId,
                                  uint32_t oldval, uint32_t newval) {
  Time now = Simulator::Now();
#if OUT
  NS_LOG_INFO(now.GetNanoSeconds()
                << " Queue size of " << nodeId << " changed from "
                << oldval << " to " << newval);
#endif
  *stream->GetStream() << "que " << now.GetNanoSeconds() << " " << nodeId
                       << " " << newval << std::endl;
}

// Trace PRU tokens
static void PruTokensInQueueDiscTrace(Ptr<OutputStreamWrapper> stream, std::string nodeId,
                                     uint16_t oldval, uint16_t newval) {
  Time now = Simulator::Now();
#if OUT
  NS_LOG_INFO(now.GetNanoSeconds()
                << " PRU Tokens of " << nodeId << " changed from "
                << oldval << " to " << newval);
#endif
  *stream->GetStream() << "pru " << now.GetNanoSeconds() << " " << nodeId
                       << " " << newval << std::endl;
}

// Trace message start events
void TraceMsgBegin(Ptr<OutputStreamWrapper> stream, Ptr<const Packet> msg,
                   Ipv4Address saddr, Ipv4Address daddr, uint16_t sport,
                   uint16_t dport, int txMsgId) {
  Time now = Simulator::Now();
#if OUT
  NS_LOG_INFO("+ " << now.GetNanoSeconds() << " " << msg->GetSize() << " "
                   << saddr << ":" << sport << " " << daddr << ":" << dport
                   << " " << txMsgId);
#endif 
  *stream->GetStream() << "+ " << now.GetNanoSeconds() << " " << msg->GetSize()
                       << " " << saddr << ":" << sport << " " << daddr << ":"
                       << dport << " " << txMsgId << std::endl;
}

// Trace message completion events
void TraceMsgAcked(Ptr<OutputStreamWrapper> stream, uint32_t msgSize,
                   Ipv4Address saddr, Ipv4Address daddr, uint16_t sport,
                   uint16_t dport, int txMsgId) {
  Time now = Simulator::Now();
#if OUT 
  NS_LOG_INFO("- " << now.GetNanoSeconds() << " " << msgSize << " " << saddr
                   << ":" << sport << " " << daddr << ":" << dport << " "
                   << txMsgId);
#endif
  *stream->GetStream() << "- " << now.GetNanoSeconds() << " " << msgSize << " "
                       << saddr << ":" << sport << " " << daddr << ":" << dport
                       << " " << txMsgId << std::endl;
}

// Track packet arrivals for measuring network utilization
void TraceDataArrival(double duration, Ptr<const Packet> msg, Ipv4Address saddr,
                      Ipv4Address daddr, uint16_t sport, uint16_t dport,
                      int txMsgId, uint32_t seqNo, uint16_t flag) {
  Time now = Simulator::Now();
  if (now.GetSeconds() <= START_TIME + duration) {
    lastDataArrivalTime = now.GetSeconds();

    Ipv4Header ipv4h;  // Consider the total pkt size for link utilization
    BoltHeader bolth;
    totalDataReceived +=
        msg->GetSize() + ipv4h.GetSerializedSize() + bolth.GetSerializedSize();
  }
}

// Create a CDF with a single value for the fixed message sizes
std::map<double, int> CreateFixedSizeCDF(uint32_t msgSize) {
  std::map<double, int> cdf;
  cdf[1.0] = msgSize;  // 100% probability of this size
  return cdf;
}

// Function to analyze PRU token data
void AnalyzePruTokens(std::string qStreamName) {
  std::ifstream qSizeTraceFile;
  qSizeTraceFile.open(qStreamName);
  NS_LOG_DEBUG("Reading PRU Token Trace From: " << qStreamName);

  std::string line;
  std::istringstream lineBuffer;

  std::map<std::string, std::vector<uint16_t>> pruTokens;
  std::string logType;
  uint64_t time;
  std::string nodeId;
  uint16_t tokenVal;
  
  while (getline(qSizeTraceFile, line)) {
    lineBuffer.clear();
    lineBuffer.str(line);
    lineBuffer >> logType;
    
    if (logType == "pru") {
      lineBuffer >> time;
      lineBuffer >> nodeId;
      lineBuffer >> tokenVal;
      pruTokens[nodeId].push_back(tokenVal);
    }
  }
  qSizeTraceFile.close();

  // Calculate statistics for each node
  for (auto it = pruTokens.begin(); it != pruTokens.end(); ++it) {
    const std::string& nodeId = it->first;
    const std::vector<uint16_t>& tokens = it->second;
    
    if (tokens.empty()) continue;
    
    uint16_t maxToken = 0;
    uint16_t avgToken = 0;
    uint64_t sum = 0;
    
    for (uint16_t t : tokens) {
      maxToken = std::max(maxToken, t);
      sum += t;
    }
    
    avgToken = static_cast<uint16_t>(sum / tokens.size());
    
    NS_LOG_UNCOND("PRU Token stats for " << nodeId << 
                  ": Max=" << maxToken << 
                  ", Avg=" << avgToken << 
                  ", Count=" << tokens.size());
  }
}

int main(int argc, char *argv[]) {
  auto simStart = std::chrono::steady_clock::now();
  AsciiTraceHelper asciiTraceHelper;

  double duration = 2.0;        // Simulation duration in seconds
  bool traceMessages = true;    // Trace message start/completion events
  bool traceQueues = true;      // Trace queue lengths
  bool traceFlowStats = true;   // Trace congestion window sizes and RTTs
  bool tracePruTokens = true;   // Trace PRU token values
  bool debugMode = false;       // Enable detailed packet traces for debugging
  uint32_t mtu = 1500;          // MTU size in bytes
  uint32_t bdpBytes = 550000;     // Bandwidth-delay product in bytes
  std::string ccMode("DEFAULT");
  uint32_t simIdx = 0;
  double workload = 0.8;

  /* Bolt (Swift) Related Parameters */
  /*
  double rttSmoothingAlpha = 0.75;    // Default: 0.75
  uint16_t topoScalingPerHop = 1000;  // Default: 1000 ns
  double maxFlowScaling = 100000.0;   // Default: 100000.0
  double maxFlowScalingCwnd = 256.0;  // Default: 256.0 pkts
  double minFlowScalingCwnd = 0.1;    // Default: 0.1 pkts
  double aiFactor = 0.1;              // Default: 1.0
  double mdFactor = 0.95;              // Default: 0.8
  double maxMd = 0.5;                 // Default: 0.5
  //uint32_t maxCwnd = bdpBytes;        // Default: 373760 Bytes
  bool usePerHopDelayForCc = false;   // Default: false
*/
  bool enableMsgAgg = true;
  bool enableBts = false;
  bool enablePru = false;
  bool enableAbs = false;
  std::string ccThreshold("3KB");

  // Setup the simulation environment
  Time::SetResolution(Time::NS);

  if (debugMode) {
    Packet::EnablePrinting();
    LogComponentEnable("BoltSimpleDumbbellSimulation", LOG_LEVEL_DEBUG);
    NS_LOG_DEBUG("Running in DEBUG Mode!");
    LogComponentEnable("MsgGeneratorApp", LOG_LEVEL_INFO); // More detailed application logs
    SeedManager::SetRun(0);
  } else {
    SeedManager::SetRun(simIdx);
  }

  // Create output directory if it doesn't exist
  std::string outputDir = "outputs";
  std::string mkdir_command = "mkdir -p " + outputDir;
  if (system(mkdir_command.c_str()) != 0) {
    NS_LOG_ERROR("Failed to create output directory");
  }

  if (ccMode == "DEFAULT") {
    enableBts = false;
    enablePru = true;
    enableAbs = false;
  }

  // Setup output file names
  std::string tracesFileName(outputDir + "/bolt-simple-dumbbell");
  tracesFileName += "_" + ccMode;
  if (debugMode)
    tracesFileName += "_debug";
  else
    tracesFileName += "_" + std::to_string(simIdx);

  std::string qStreamName = tracesFileName + ".qlen";
  std::string msgTracesFileName = tracesFileName + ".tr";
  std::string statsTracesFileName = tracesFileName + ".log";
  std::string pruTracesFileName = tracesFileName + ".pru";

  // Create the nodes
  NS_LOG_DEBUG("Creating Nodes...");
  NodeContainer clientNodes;   // C1, C2
  clientNodes.Create(2);
  
  NodeContainer serverNodes;   // C3, C4
  serverNodes.Create(2);
  
  NodeContainer switchNodes;   // S1, S2
  switchNodes.Create(2);

  // Configure the channels
  NS_LOG_DEBUG("Configuring Channels...");

  // C1-S1 link (10us delay)
  PointToPointHelper c1s1Link;
  c1s1Link.SetDeviceAttribute("DataRate", StringValue("10Gbps"));
  c1s1Link.SetChannelAttribute("Delay", StringValue("10us")); // One-way delay
  c1s1Link.SetQueue("ns3::DropTailQueue", "MaxSize", StringValue("1p"));

  // C2-S1 link (2us delay)
  PointToPointHelper c2s1Link;
  c2s1Link.SetDeviceAttribute("DataRate", StringValue("10Gbps"));
  c2s1Link.SetChannelAttribute("Delay", StringValue("2us")); // One-way delay
  c2s1Link.SetQueue("ns3::DropTailQueue", "MaxSize", StringValue("1p"));

  // S1-S2 link (2us delay) - BOTTLENECK LINK
  PointToPointHelper s1s2Link;
  s1s2Link.SetDeviceAttribute("DataRate", StringValue("10Gbps")); // Bottleneck link
  s1s2Link.SetChannelAttribute("Delay", StringValue("2us")); // One-way delay
  s1s2Link.SetQueue("ns3::DropTailQueue", "MaxSize", StringValue("1p"));

  // S2-C3 link (10us delay)
  PointToPointHelper s2c3Link;
  s2c3Link.SetDeviceAttribute("DataRate", StringValue("10Gbps"));
  s2c3Link.SetChannelAttribute("Delay", StringValue("10us")); // One-way delay
  s2c3Link.SetQueue("ns3::DropTailQueue", "MaxSize", StringValue("1p"));

  // S2-C4 link (2us delay)
  PointToPointHelper s2c4Link;
  s2c4Link.SetDeviceAttribute("DataRate", StringValue("10Gbps"));
  s2c4Link.SetChannelAttribute("Delay", StringValue("2us")); // One-way delay
  s2c4Link.SetQueue("ns3::DropTailQueue", "MaxSize", StringValue("1p"));

  // Create the NetDevices and install them on nodes
  NS_LOG_DEBUG("Creating NetDevices...");
  NetDeviceContainer c1s1Devices = c1s1Link.Install(clientNodes.Get(0), switchNodes.Get(0));
  NetDeviceContainer c2s1Devices = c2s1Link.Install(clientNodes.Get(1), switchNodes.Get(0));
  NetDeviceContainer s1s2Devices = s1s2Link.Install(switchNodes.Get(0), switchNodes.Get(1));
  NetDeviceContainer s2c3Devices = s2c3Link.Install(switchNodes.Get(1), serverNodes.Get(0));
  NetDeviceContainer s2c4Devices = s2c4Link.Install(switchNodes.Get(1), serverNodes.Get(1));

  // Set MTU for all devices
  for (uint32_t i = 0; i < c1s1Devices.GetN(); i++) c1s1Devices.Get(i)->SetMtu(mtu);
  for (uint32_t i = 0; i < c2s1Devices.GetN(); i++) c2s1Devices.Get(i)->SetMtu(mtu);
  for (uint32_t i = 0; i < s1s2Devices.GetN(); i++) s1s2Devices.Get(i)->SetMtu(mtu);
  for (uint32_t i = 0; i < s2c3Devices.GetN(); i++) s2c3Devices.Get(i)->SetMtu(mtu);
  for (uint32_t i = 0; i < s2c4Devices.GetN(); i++) s2c4Devices.Get(i)->SetMtu(mtu);

  // Install Internet Stack
  NS_LOG_DEBUG("Installing Internet Stack...");

  // Set Bolt parameters
  Config::SetDefault("ns3::BoltL4Protocol::AggregateMsgsIfPossible",
    BooleanValue(enableMsgAgg));
  Config::SetDefault("ns3::BoltL4Protocol::CcMode", StringValue(ccMode));
  Config::SetDefault("ns3::BoltL4Protocol::BandwidthDelayProduct",
    UintegerValue(bdpBytes));
/*
  
  
  Config::SetDefault("ns3::Ipv4GlobalRouting::EcmpMode", EnumValue(Ipv4GlobalRouting::ECMP_PER_FLOW));
  Config::SetDefault("ns3::BoltL4Protocol::AiFactor", DoubleValue(aiFactor));
  Config::SetDefault("ns3::BoltL4Protocol::MdFactor", DoubleValue(mdFactor));
  Config::SetDefault("ns3::BoltL4Protocol::MaxMd", DoubleValue(maxMd));
  Config::SetDefault("ns3::BoltL4Protocol::RttSmoothingAlpha",
    DoubleValue(rttSmoothingAlpha));
  Config::SetDefault("ns3::BoltL4Protocol::TopoScalingPerHop",
    UintegerValue(topoScalingPerHop));
  Config::SetDefault("ns3::BoltL4Protocol::MaxFlowScaling",
    DoubleValue(maxFlowScaling));
  Config::SetDefault("ns3::BoltL4Protocol::MaxFlowScalingCwnd",
    DoubleValue(maxFlowScalingCwnd));
  Config::SetDefault("ns3::BoltL4Protocol::MinFlowScalingCwnd",
    DoubleValue(minFlowScalingCwnd));
  Config::SetDefault("ns3::BoltL4Protocol::UsePerHopDelayForCc",
    BooleanValue(usePerHopDelayForCc));
*/
  InternetStackHelper stack;
  stack.InstallAll();

  // Setup BOLT queue discipline
  TrafficControlHelper boltQdisc;
  boltQdisc.SetRootQueueDisc(
      "ns3::PfifoBoltQueueDisc", "MaxSize", StringValue("1000p"), "EnableBts",
      BooleanValue(enableBts), "CcThreshold", StringValue(ccThreshold), "EnablePru",
      BooleanValue(enablePru), "MaxInstAvailLoad", IntegerValue(mtu), "EnableAbs",
      BooleanValue(enableAbs));

  // Install queue discipline on all devices and trace them
  Ptr<OutputStreamWrapper> qStream = asciiTraceHelper.CreateFileStream(qStreamName);
  Ptr<OutputStreamWrapper> pruStream = asciiTraceHelper.CreateFileStream(pruTracesFileName);
  // Install on client to switch links
  QueueDiscContainer c1s1Qdisc = boltQdisc.Install(c1s1Devices);
  QueueDiscContainer c2s1Qdisc = boltQdisc.Install(c2s1Devices);
  
  // Install on switch to switch link (this is our bottleneck)
  QueueDiscContainer s1s2Qdisc = boltQdisc.Install(s1s2Devices);
  
  // Install on switch to server links
  QueueDiscContainer s2c3Qdisc = boltQdisc.Install(s2c3Devices);
  QueueDiscContainer s2c4Qdisc = boltQdisc.Install(s2c4Devices);

  // Set up queue and PRU tracing if enabled
  if (traceQueues) {
    // Trace S1 queue (bottleneck for C1->C3 and C2->C4)
    s1s2Qdisc.Get(0)->TraceConnectWithoutContext(
        "BytesInQueue",
        MakeBoundCallback(&BytesInQueueDiscTrace, qStream, "S1-S2"));
    
    // Trace S2 queues
    s2c3Qdisc.Get(0)->TraceConnectWithoutContext(
        "BytesInQueue",
        MakeBoundCallback(&BytesInQueueDiscTrace, qStream, "S2-C3"));
    
    s2c4Qdisc.Get(0)->TraceConnectWithoutContext(
        "BytesInQueue",
        MakeBoundCallback(&BytesInQueueDiscTrace, qStream, "S2-C4"));
  }
  
  if (tracePruTokens) {
    s1s2Qdisc.Get(0)->TraceConnectWithoutContext(
        "PruTokensInQueue",
        MakeBoundCallback(&PruTokensInQueueDiscTrace, pruStream, "S1-S2"));

  }

  // Assign IP addresses
  Ipv4AddressHelper address;
  address.SetBase("10.1.1.0", "255.255.255.0");

  // C1-S1 link
  Ipv4InterfaceContainer c1s1IPs = address.Assign(c1s1Devices);
  address.NewNetwork();

  // C2-S1 link
  Ipv4InterfaceContainer c2s1IPs = address.Assign(c2s1Devices);
  address.NewNetwork();

  // S1-S2 link
  Ipv4InterfaceContainer s1s2IPs = address.Assign(s1s2Devices);
  address.NewNetwork();

  // S2-C3 link
  Ipv4InterfaceContainer s2c3IPs = address.Assign(s2c3Devices);
  address.NewNetwork();

  // S2-C4 link
  Ipv4InterfaceContainer s2c4IPs = address.Assign(s2c4Devices);
  address.NewNetwork();

  // Build routing tables
  Ipv4GlobalRoutingHelper::PopulateRoutingTables();

  // Create the applications
  NS_LOG_DEBUG("Installing the Applications...");
  
  // Server addresses
  InetSocketAddress c3Addr(s2c3IPs.GetAddress(1), 1000); // C3
  InetSocketAddress c4Addr(s2c4IPs.GetAddress(1), 1001); // C4
  
  // Setup applications on servers to receive data
  PacketSinkHelper sinkHelper("ns3::BoltSocketFactory", InetSocketAddress(Ipv4Address::GetAny(), 0));
  ApplicationContainer sinkApps;
  
  // C3 server
  sinkHelper.SetAttribute("Local", AddressValue(InetSocketAddress(Ipv4Address::GetAny(), 1000)));
  sinkApps.Add(sinkHelper.Install(serverNodes.Get(0)));
  
  // C4 server
  sinkHelper.SetAttribute("Local", AddressValue(InetSocketAddress(Ipv4Address::GetAny(), 1001)));
  sinkApps.Add(sinkHelper.Install(serverNodes.Get(1)));
  
  sinkApps.Start(Seconds(START_TIME));
  sinkApps.Stop(Seconds(START_TIME + duration));
  
   // Set up parameters for continuous message sending
   uint32_t c1MsgSize = 1000 * 1000 / 8;   // Smaller message size for more frequent sending (500Kb)
   uint32_t c2MsgSize = 1000 * 1000 / 8;   // Larger message size (1Mb)
   BoltHeader bolth;
   Ipv4Header ipv4h;
   uint32_t payloadSize =
       mtu - bolth.GetSerializedSize() - ipv4h.GetSerializedSize();
   // Configure MsgGeneratorApp for continuous sending
   //Config::SetDefault("ns3::MsgGeneratorApp::MaxMsg", UintegerValue(1)); // Send 100 messages
   Config::SetDefault("ns3::MsgGeneratorApp::PayloadSize", UintegerValue(payloadSize)); // MTU - IP/TCP headers
   Config::SetDefault("ns3::MsgGeneratorApp::UnitsInBytes", BooleanValue(true)); // Use bytes for units 
   Config::SetDefault("ns3::MsgGeneratorApp::StaticMsgSize",UintegerValue(1250000 * 20));
  // Client applications container
  ApplicationContainer clientApps;
  
  // Create C1's application (sending to C3)
  Ptr<MsgGeneratorApp> c1App = CreateObject<MsgGeneratorApp>(c1s1IPs.GetAddress(0), 2000);
  std::vector<InetSocketAddress> c1Dest;
  c1Dest.push_back(c3Addr);
  c1App->Install(clientNodes.Get(0), c1Dest);
  
  // Create workload distribution for C1
  double avgMsgSize1 = c1MsgSize;
  std::map<double, int> c1MsgSizeCDF = CreateFixedSizeCDF(c1MsgSize);
  // Set workload to 1.0 (full link capacity)
  c1App->SetWorkload(workload, c1MsgSizeCDF, avgMsgSize1);
  c1App->SetAttribute("MaxMsg", UintegerValue(1));
  clientApps.Add(c1App);
  
  // Create C2's application (sending to C4)
  Ptr<MsgGeneratorApp> c2App = CreateObject<MsgGeneratorApp>(c2s1IPs.GetAddress(0), 2001);
  std::vector<InetSocketAddress> c2Dest;
  c2Dest.push_back(c4Addr);
  c2App->Install(clientNodes.Get(1), c2Dest);
  
  // Create workload distribution for C2
  double avgMsgSize2 = c2MsgSize;
  std::map<double, int> c2MsgSizeCDF = CreateFixedSizeCDF(c2MsgSize);
  // Set workload to 1.0 (full link capacity)
  c2App->SetWorkload(workload, c2MsgSizeCDF, avgMsgSize2);
  c2App->SetAttribute("MaxMsg", UintegerValue(2));
  clientApps.Add(c2App);
  

  c1App->Start(Seconds(START_TIME));
  c1App->Stop(Seconds(START_TIME + duration));
  
  // C2 runs for the full duration
  c2App->Start(Seconds(START_TIME ));
  c2App->Stop(Seconds(START_TIME + duration));

  // Log the start of the applications
  NS_LOG_INFO("C1 will send to C3 from " << START_TIME << "s to " << (START_TIME + duration) << "s");
  NS_LOG_INFO("C2 will send to C4 from " << START_TIME << "s to " << (START_TIME + duration) << "s");

  // Enable message tracing if requested
  if (traceMessages) {
    Ptr<OutputStreamWrapper> msgStream = asciiTraceHelper.CreateFileStream(msgTracesFileName);
    Config::ConnectWithoutContext("/NodeList/*/$ns3::BoltL4Protocol/MsgBegin",
                                  MakeBoundCallback(&TraceMsgBegin, msgStream));
    Config::ConnectWithoutContext("/NodeList/*/$ns3::BoltL4Protocol/MsgAcked",
                                  MakeBoundCallback(&TraceMsgAcked, msgStream));
  }

  // Enable flow statistics tracing if requested
  if (traceFlowStats) {
    Ptr<OutputStreamWrapper> statsStream = asciiTraceHelper.CreateFileStream(statsTracesFileName);
    Config::ConnectWithoutContext("/NodeList/*/$ns3::BoltL4Protocol/FlowStats",
                                  MakeBoundCallback(&TraceFlowStats, statsStream));
  }

  // Connect data arrival trace for measuring utilization
  Config::ConnectWithoutContext("/NodeList/*/$ns3::BoltL4Protocol/DataPktArrival",
                               MakeBoundCallback(&TraceDataArrival, duration));

  // Run the simulation
  NS_LOG_WARN("Running the Simulation...");
  Simulator::Stop(Seconds(START_TIME + duration));
  Simulator::Run();
  Simulator::Destroy();

  // Calculate network utilization
  double totalUtilization = (double)totalDataReceived * 8.0 / 1e9 /
                           (lastDataArrivalTime - START_TIME);
  NS_LOG_UNCOND("Total utilization: " << totalUtilization << "Gbps");
  
  // Analyze PRU token data if tracing was enabled
  if (tracePruTokens) {
    AnalyzePruTokens(qStreamName);
  }

  // Calculate simulation runtime
  auto simStop = std::chrono::steady_clock::now();
  auto simTime = std::chrono::duration_cast<std::chrono::seconds>(simStop - simStart);
  NS_LOG_UNCOND("Time taken by simulation: " << simTime.count() << " seconds");

  return 0;
}