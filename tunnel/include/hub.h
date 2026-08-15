#ifndef SDTP_HUB_H
#define SDTP_HUB_H

#include <net/if.h>
#include <netinet/in.h>
#include <time.h>
#include <stdint.h>

#include "sdtp.h"

#define SDTP_HUB_MAX_PEERS 64

typedef struct {
    uint8_t static_pk[SDTP_KEY_LEN];
    uint32_t tunnel_ip;
    sdtp_session session;
    struct sockaddr_in addr;
    int have_addr;
    int established;
    uint64_t last_peer_ts;
    time_t last_recv;
    time_t last_send;
} sdtp_hub_peer;

typedef struct {
    sdtp_keypair my_static;
    char address[64];
    uint32_t self_ip;
    uint16_t listen_port;
    int mtu;
    char ifname[IFNAMSIZ];
    sdtp_hub_peer peers[SDTP_HUB_MAX_PEERS];
    size_t peer_count;
} sdtp_hub_config;

int sdtp_hub_parse_ipv4_dst(const uint8_t *pkt, size_t len, uint32_t *dst_out);
int sdtp_hub_find_peer_by_session_id(const sdtp_hub_peer *peers, size_t n,
                                     const uint8_t session_id[SDTP_SESSION_ID_LEN]);
int sdtp_hub_find_peer_by_ip(const sdtp_hub_peer *peers, size_t n, uint32_t ip);
int sdtp_hub_config_load(const char *path, sdtp_hub_config *cfg);
void sdtp_hub_run(int tun_fd, int udp_fd, sdtp_hub_config *cfg);

#endif /* SDTP_HUB_H */
