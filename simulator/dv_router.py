"""
Your awesome Distance Vector router for CS 168

Based on skeleton code by:
  MurphyMc, zhangwen0411, lab352
"""

import sim.api as api
from cs168.dv import (
    RoutePacket,
    Table,
    TableEntry,
    DVRouterBase,
    Ports,
    FOREVER,
    INFINITY,
)


class DVRouter(DVRouterBase):

    # A route should time out after this interval
    ROUTE_TTL = 15

    # -----------------------------------------------
    # At most one of these should ever be on at once
    SPLIT_HORIZON = False
    POISON_REVERSE = False
    # -----------------------------------------------

    # Determines if you send poison for expired routes
    POISON_EXPIRED = False

    # Determines if you send updates when a link comes up
    SEND_ON_LINK_UP = False

    # Determines if you send poison when a link goes down
    POISON_ON_LINK_DOWN = False

    def __init__(self):
        """
        Called when the instance is initialized.
        DO NOT remove any existing code from this method.
        However, feel free to add to it for memory purposes in the final stage!
        """
        assert not (
            self.SPLIT_HORIZON and self.POISON_REVERSE
        ), "Split horizon and poison reverse can't both be on"

        self.start_timer()  # Starts signaling the timer at correct rate.

        # Contains all current ports and their latencies.
        # See the write-up for documentation.
        self.ports = Ports()

        # This is the table that contains all current routes
        self.table = Table()
        self.table.owner = self

        ##### Begin Stage 10A #####
        self.history = {}

        ##### End Stage 10A #####

    def add_static_route(self, host, port):
        """
        Adds a static route to this router's table.

        Called automatically by the framework whenever a host is connected
        to this router.

        :param host: the host.
        :param port: the port that the host is attached to.
        :returns: nothing.
        """
        # `port` should have been added to `peer_tables` by `handle_link_up`
        # when the link came up.
        assert port in self.ports.get_all_ports(), "Link should be up, but is not."

        ##### Begin Stage 1 #####
        lat = self.ports.get_latency(port)
        self.table[host] = TableEntry(host, port,lat, FOREVER)
        self.send_routes(force=False)
        ##### End Stage 1 #####

    def handle_data_packet(self, packet, in_port):
        """
        Called when a data packet arrives at this router.

        You may want to forward the packet, drop the packet, etc. here.

        :param packet: the packet that arrived.
        :param in_port: the port from which the packet arrived.
        :return: nothing.
        """
        
        ##### Begin Stage 2 #####
        # if dest does not exist, drop
        # else -> check latency: if either the forward it 
        dest = packet.dst
        entry = self.table.get(dest)
        if entry is None:
            return 
        
        next_hop = entry.port
        if self.ports.get_latency(next_hop) >= INFINITY:
            return 
        
        if entry.latency >= INFINITY:
            return
        
        self.send(packet,port=next_hop)

        ##### End Stage 2 #####

    def send_routes(self, force=False, single_port=None):
        """
        Send route advertisements for all routes in the table.

        :param force: if True, advertises ALL routes in the table;
                      otherwise, advertises only those routes that have
                      changed since the last advertisement.
               single_port: if not None, sends updates only to that port; to
                            be used in conjunction with handle_link_up.
        :return: nothing.
        """
        
        ##### Begin Stages 3, 6, 7, 8, 10 #####
        # we are a router, we send our dest, costs to other neibor routers
        # call add static route for each neirboring port 
        target_ports = [single_port] if single_port is not None else self.ports.get_all_ports()
        for outbound_port in target_ports:
            if outbound_port not in self.history:
                self.history[outbound_port] = {}

            for destination, route_entry in self.table.items():
                if self.SPLIT_HORIZON and route_entry.port == outbound_port:
                    continue 
                elif self.POISON_REVERSE and route_entry.port == outbound_port:
                    advertised_latency = INFINITY
                else:
                    advertised_latency = min(route_entry.latency, INFINITY)

                previous_announcement = self.history[outbound_port].get(destination)
                if not force and previous_announcement == advertised_latency:
                    continue

                self.send_route(outbound_port, destination, advertised_latency)
                
                self.history[outbound_port][destination] = advertised_latency

        ##### End Stages 3, 6, 7, 8, 10 #####

    def expire_routes(self):
        """
        Clears out expired routes from table.
        accordingly.
        """
        ##### Begin Stages 5, 9 #####
        expired_destinations = [
            dst for dst, entry in self.table.items() if entry.has_expired
        ]
        for dst in expired_destinations:
            self.s_log(f"Route to {dst} timed out.")

            if self.POISON_EXPIRED:
                self.table[dst] = TableEntry(
                    dst=dst,
                    port=self.table[dst].port,
                    latency=INFINITY,
                    expire_time=api.current_time() + self.ROUTE_TTL,
                )
            else:
                self.table.pop(dst)
        if expired_destinations:
            self.send_routes(force=False)

        ##### End Stages 5, 9 #####

    def handle_route_advertisement(self, route_dst, route_latency, port):
        """
        Called when the router receives a route advertisement from a neighbor.

        :param route_dst: the destination of the advertised route.
        :param route_latency: latency from the neighbor to the destination.
        :param port: the port that the advertisement arrived on.
        :return: nothing.
        """
        
        ##### Begin Stages 4, 10 #####
        link_cost = self.ports.get_latency(port)
        path_latency = min(route_latency + link_cost, INFINITY) # Stage 8/10 cap
        
        existing_entry = self.table.get(route_dst)
        should_update_table = False
        changed_for_neighbors = False # This is the Stage 10 trigger

        if existing_entry is None:
            if path_latency < INFINITY:
                should_update_table = True
                changed_for_neighbors = True
        elif port == existing_entry.port:
            # Rule 2: Always update table to refresh timeout
            should_update_table = True
            # Stage 10: Only trigger neighbors if the cost actually shifted
            if path_latency != existing_entry.latency:
                changed_for_neighbors = True
        elif path_latency < existing_entry.latency:
            # Rule 1: Strictly better path
            should_update_table = True
            changed_for_neighbors = True

        if should_update_table:
            self.table[route_dst] = TableEntry(
                dst=route_dst,
                port=port,
                latency=path_latency,
                expire_time=api.current_time() + self.ROUTE_TTL
            )

        # Triggered Update: Tell neighbors NOW if the path changed
        if changed_for_neighbors:
            self.send_routes(force=False)

    def handle_link_up(self, port, latency):
        """
        Called by the framework when a link attached to this router goes up.

        :param port: the port that the link is attached to.
        :param latency: the link latency.
        :returns: nothing.
        """
        self.ports.add_port(port, latency)

        ##### Begin Stage 10B #####
        if self.SEND_ON_LINK_UP:
            self.send_routes(force=True, single_port=port)

        ##### End Stage 10B #####

    def handle_link_down(self, port):
        """
        Called by the framework when a link attached to this router goes down.

        :param port: the port number used by the link.
        :returns: nothing.
        """
        ##### Begin Stage 10B #####
        self.ports.remove_port(port)
        if port in self.history:
            self.history.pop(port)

        affected_destinations = [
            dst for dst, entry in self.table.items() if entry.port == port
        ]

        for dst in affected_destinations:
            if self.POISON_ON_LINK_DOWN:
                self.table[dst] = TableEntry(
                    dst=dst,
                    port=port,
                    latency=INFINITY,
                    expire_time=api.current_time() + self.ROUTE_TTL
                )
            else:
                self.table.pop(dst)

        if affected_destinations:
            self.send_routes(force=False)
        ##### End Stage 10B #####

    # Feel free to add any helper methods!
