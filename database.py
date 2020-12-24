#!/usr/bin/env python3

"""
database.py

A series of functions to leverage the (node, edge) schema of 
json-based nodes, and edges with optional json properties,
using an atomic transaction wrapper function.

"""

import sqlite3
import json

def atomic(db_file, cursor_exec_fn):
    connection = sqlite3.connect(db_file)
    cursor = connection.cursor()
    results = cursor_exec_fn(cursor)
    connection.commit()
    connection.close()
    return results

def initialize(db_file, schema_file='schema.sql'):
    def _init(cursor):
        with open(schema_file) as f:
            for statement in f.read().split(';'):
                cursor.execute(statement)
    return atomic(db_file, _init)

def _set_id(identifier, data):
    if identifier is not None:
        data["id"] = identifier
    return data

def add_node(data, identifier=None):
    def _add_node(cursor):
        cursor.execute("INSERT INTO nodes VALUES(json(?))", (json.dumps(_set_id(identifier, data)),))
    return _add_node

def upsert_node(identifier, data):
    def _upsert_node(cursor):
        current_data = find_node(identifier)(cursor)
        updated_data = {**current_data, **data}
        cursor.execute("UPDATE nodes SET body = json(?) WHERE id = ?", (json.dumps(_set_id(identifier, updated_data)), identifier,))
    return _upsert_node

def connect_nodes(source_id, target_id, properties={}):
    def _connect_nodes(cursor):
        cursor.execute("INSERT INTO edges VALUES(?, ?, json(?))", (source_id, target_id, json.dumps(properties),))
    return _connect_nodes

def remove_node(identifier):
    def _remove_node(cursor):
        cursor.execute("DELETE FROM edges WHERE source = ? OR target = ?", (identifier, identifier,))
        cursor.execute("DELETE FROM nodes WHERE id = ?", (identifier,))
    return _remove_node

def _parse_search_results(results, idx=0):
    return [json.loads(item[idx]) for item in results]

def find_node(identifier):
    def _find_node(cursor):
        results = cursor.execute("SELECT body FROM nodes WHERE json_extract(body, '$.id') = ?", (identifier,)).fetchall()
        if len(results) == 1:
            return _parse_search_results(results).pop()
        return {}
    return _find_node

def _search_where(properties, predicate='='):
    return " AND ".join(["json_extract(body, '$.{}') {} ?".format(k, predicate) for k in properties.keys()])

def _search_like(properties):
    return _search_where(properties, 'LIKE')

def _search_equals(properties):
    return tuple([str(v) for v in properties.values()])

def _search_starts_with(properties):
    return tuple([str(v)+'%' for v in properties.values()])

def _search_contains(properties):
    return tuple(['%'+str(v)+'%' for v in properties.values()])

def find_nodes(data, where_fn=_search_where, search_fn=_search_equals):
    def _find_nodes(cursor):
        return _parse_search_results(cursor.execute("SELECT body FROM nodes WHERE {}".format(where_fn(data)), search_fn(data)).fetchall())
    return _find_nodes

def find_neighbors(identifier):
    def _find_neighbors(cursor):
        return cursor.execute("SELECT * FROM edges WHERE source = ? OR target = ?", (identifier, identifier,)).fetchall()
    return _find_neighbors

def find_outbound_neighbors(identifier):
    def _find_outbound_neighbors(cursor):
        return cursor.execute("SELECT * FROM edges WHERE source = ?", (identifier,)).fetchall()
    return _find_outbound_neighbors

def find_inbound_neighbors(identifier):
    def _find_inbound_neighbors(cursor):
        return cursor.execute("SELECT * FROM edges WHERE target = ?", (identifier,)).fetchall()
    return _find_inbound_neighbors

def _get_edge_sources(results):
    return _parse_search_results(results, 0)

def _get_edge_targets(results):
    return _parse_search_results(results, 1)

def _get_edge_properties(results):
    return _parse_search_results(results, 2)

def traverse (db_file, src, tgt=None, neighbors_fn=find_neighbors):
    def _depth_first_search(cursor):
        path = []
        queue = []
        source_node = atomic(db_file, find_node(src))
        if source_node:
            queue.append(source_node)
        while queue:
            node = queue.pop()
            if node not in path:
                path.append(node)
                if node['id'] == tgt:
                    break
                neighbors = atomic(db_file, neighbors_fn(node['id']))
                for identifier in set(_get_edge_sources(neighbors)).union(_get_edge_targets(neighbors)):
                    neighbor = atomic(db_file, find_node(identifier))
                    if neighbor:
                        queue.append(neighbor)
        return path
    return atomic(db_file, _depth_first_search)