package com.mycompany.ledger;

import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.io.OutputStream;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

// Ledger team's app (real-estate epic, ticket 08). Plain JDK HttpServer,
// no framework -- the point of this app is the log4j 2.14 dependency
// (Log4Shell-era, CVE-2021-44228), not the web framework.
public class Ledger {
  private static final Logger log = LogManager.getLogger(Ledger.class);

  public static void main(String[] args) throws Exception {
    HttpServer server = HttpServer.create(new InetSocketAddress(8080), 0);
    server.createContext("/", exchange -> {
      log.info("request from {}", exchange.getRemoteAddress());
      byte[] body = "ledger\n".getBytes();
      exchange.sendResponseHeaders(200, body.length);
      try (OutputStream os = exchange.getResponseBody()) {
        os.write(body);
      }
    });
    log.info("ledger starting on :8080");
    server.start();
  }
}
