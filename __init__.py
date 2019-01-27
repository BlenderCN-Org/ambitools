﻿# ##### BEGIN GPL LICENSE BLOCK #####
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, version 3 of the license.

#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# ##### END GPL LICENSE BLOCK #####

# import/reload all source files
if not "bpy" in locals():
    from . import amb_utils as au
    from . import amb_fastmesh as afm
    from . import amb_bmesh as abm
else:
    import importlib
    importlib.reload(au)
    importlib.reload(afm)
    importlib.reload(abm)


import bpy # pylint: disable=import-error
import numpy as np
import bmesh # pylint: disable=import-error
import random
from collections import defaultdict, OrderedDict
import mathutils as mu # pylint: disable=import-error


class Mesh_Operator(bpy.types.Operator):
    bl_options = {'REGISTER', 'UNDO'}
    my_props = []
    prefix = ""
    parent_name = ""

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def payload(self, mesh, context):
        pass

    def invoke(self, context, event):
        #self.pr = au.profiling_start()

        # copy property values from panel to operator
        print(self.prefix, self.my_props)
        if self.prefix != "":
            for p in self.my_props:
                opname = self.parent_name + "_" + self.prefix + "_" + p
                setattr(self, p, getattr(context.scene, opname)) 
                print(opname, getattr(context.scene, opname))

        return self.execute(context)

    def execute(self, context):
        # apply modifiers for the active object before mesh actions
        for mod in context.active_object.modifiers:
            try:
                bpy.ops.object.modifier_apply(modifier=mod.name)
            except RuntimeError as ex:
                print(ex)    

        # run mesh operation
        mesh = context.active_object.data
        self.payload(mesh, context)
        #mesh.update(calc_edges=True)

        #au.profiling_end(self.pr)

        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        
        for p in self.my_props:
            row = col.row()
            row.prop(self, p, expand=True)

def mesh_operator_factory(props, prefix, payload, name, parent_name):
    return type(name, (Mesh_Operator,), 
        {**{'bl_idname' : "object." + parent_name + "_" + prefix,
        'bl_label' : " ".join(prefix.split("_")).capitalize(),
        'my_props' : props.keys(),
        'prefix' : prefix,
        'parent_name' : parent_name,
        'payload' : payload
        }, ** props})

class PanelBuilder:
    def __init__(self, master_name, master_panel, mesh_ops):
        self.panel = {i.prefix : bpy.props.BoolProperty(
                name=i.prefix.capitalize() + " settings",
                description="Display settings of the tool",
                default=False) for i in mesh_ops}      

        self.master_name = master_name
        self.master_panel = master_panel
        self.mesh_ops = mesh_ops

    def create_panel(this): # pylint: disable=E0213
        class _pt(bpy.types.Panel):
            bl_label = " ".join([i.capitalize() for i in this.master_name.split("_")])
            bl_idname = this.master_panel

            bl_space_type = 'VIEW_3D'
            bl_region_type = 'UI'
            #bl_category = "Tools"

            def draw(self, context):
                layout = self.layout
                col = layout.column(align=True)

                for mop in this.mesh_ops:
                    split = col.split(factor=0.15, align=True)
                    opname = this.master_panel + "_" + mop.prefix
                    
                    if len(mop.props) == 0:
                        split.prop(context.scene, opname, text="", icon='LINK')
                    else:
                        if getattr(context.scene, opname):
                            split.prop(context.scene, opname, text="", icon='DOWNARROW_HLT')
                        else:
                            split.prop(context.scene, opname, text="", icon='RIGHTARROW')

                    split.operator(mop.op.bl_idname, text = " ".join(mop.prefix.split("_")).capitalize())

                    if getattr(context.scene, opname):
                        box = col.column(align=True).box().column()
                        for i, p in enumerate(mop.props):
                            if i%2==0:
                                row = box.row(align=True)
                            row.prop(context.scene, this.master_name+"_"+mop.prefix + "_" + p)
        return _pt

    def register_params(self):
        for mesh_op in self.mesh_ops:
            bpy.utils.register_class(mesh_op.op)
            for k, v in mesh_op.props.items():
                setattr(bpy.types.Scene, mesh_op.parent_name+"_"+mesh_op.prefix+"_"+k, v)

        for k, v in self.panel.items():
            setattr(bpy.types.Scene, self.master_panel+"_"+k, v)

    def unregister_params(self):
        for mesh_op in self.mesh_ops:
            bpy.utils.unregister_class(mesh_op.op)
            for k, _ in mesh_op.props.items():
                delattr(bpy.types.Scene, mesh_op.parent_name+"_"+mesh_op.prefix+"_"+k)

        for k, _ in self.panel.items():
            delattr(bpy.types.Scene, self.master_panel+"_"+k)


class Master_OP:
    def generate(self):
        pass

    def __init__(self):
        self.props = OrderedDict()
        self.parent_name = "mesh_refine_toolbox"

        self.start_mode = ""
        self.payload = lambda a, b, c: 0
        self.prefix = ""
        self.name = ""

        self.generate()

        if hasattr(self, 'start_mode'):
            def _wrap(this, mesh, context):
                mode = context.object.mode
                bpy.ops.object.mode_set(mode = self.start_mode)
                self.payload(this, mesh, context)
                bpy.ops.object.mode_set(mode = mode)

            self.op = mesh_operator_factory(self.props, self.prefix, _wrap, self.name, self.parent_name)
        else:
            self.op = mesh_operator_factory(self.props, self.prefix, self.payload, self.name, self.parent_name)

class Masked_Smooth_OP(Master_OP):
    def generate(self):
        self.props['power']  = bpy.props.FloatProperty(name="Power", default=0.7, min=0.0, max=10.0)
        self.props['iter']   = bpy.props.IntProperty(name="Iterations", default=2, min=1, max=10)
        self.props['border'] = bpy.props.BoolProperty(name="Exclude border", default=True)

        self.prefix = "masked_smooth"
        self.name = "OBJECT_OT_Maskedsmooth"
        self.start_mode = 'OBJECT'

        def _pl(self, mesh, context):
            verts = afm.read_verts(mesh)
            edges = afm.read_edges(mesh)
            norms = afm.read_norms(mesh)

            curve = np.abs(afm.calc_curvature(verts, edges, norms)-0.5)
            curve = afm.mesh_smooth_filter_variable(curve, verts, edges, 1)
            
            curve -= np.min(curve)
            curve /= np.max(curve)
            curve *= 8.0 * self.power
            curve = np.where(curve>1.0, 1.0, curve)

            # don't move border
            if self.border:
                curve = np.where(abm.get_nonmanifold_verts(mesh), 1.0, curve)

            new_verts = afm.op_smooth_mask(verts, edges, curve, self.iter)

            afm.write_verts(mesh, new_verts)

            mesh.update(calc_edges=True)

        self.payload = _pl

class CropToLarge_OP(Master_OP):
    def generate(self):
        self.props['shells'] = bpy.props.IntProperty(name="Shells", default=1, min=1, max=100)

        self.prefix = "crop_to_large"
        self.name = "OBJECT_OT_CropToLarge"
        self.start_mode = 'EDIT'

        def _pl(self, mesh, context):
            with abm.Bmesh_from_edit(mesh) as bm:
                shells = abm.mesh_get_edge_connection_shells(bm)
                print(len(shells), "shells")

                for i in range(len(bm.faces)):
                    bm.faces[i].select = True

                delete_this = list(sorted(shells, key=lambda x: -len(x)))[:self.shells]
                for s in delete_this:
                    for f in s:
                        bm.faces[f.index].select = False

            bpy.ops.mesh.delete(type='FACE')

        self.payload = _pl

class MergeTiny_OP(Master_OP):
    def generate(self):
        self.props['threshold'] = bpy.props.FloatProperty(name="Threshold", default=0.02, min=0.0, max=1.0)

        self.prefix = "merge_tiny_faces"
        self.name = "OBJECT_OT_MergeTinyFaces"
        self.start_mode = 'EDIT'

        def _pl(self, mesh, context):
            with abm.Bmesh_from_edit(mesh) as bm:
                # thin faces
                collapse_these = []
                avg = sum(f.calc_perimeter() for f in bm.faces)/len(bm.faces)
                for f in bm.faces:
                    if f.calc_perimeter() < avg * self.threshold:
                        collapse_these.extend(f.edges)

                bmesh.ops.collapse(bm, edges=list(set(collapse_these)))
                bmesh.ops.connect_verts_concave(bm, faces=bm.faces)

        self.payload = _pl

class EvenEdges_OP(Master_OP):
    def generate(self):
        self.props['amount'] = bpy.props.FloatProperty(name="Amount", default=1.0, min=0.0, max=1.0)
        self.props['iterations'] = bpy.props.IntProperty(name="Iterations", default=1, min=1, max=20)

        self.prefix = "make_even_edges"
        self.name = "OBJECT_OT_MakeEvenEdges"
        self.start_mode = 'EDIT'

        def _pl(self, mesh, context):
            with abm.Bmesh_from_edit(mesh) as bm:
                avg = sum(e.calc_length() for e in bm.edges)/len(bm.edges)
                for _ in range(self.iterations):
                    for e in bm.edges:
                        grow = (avg - e.calc_length())/2*self.amount
                        center = (e.verts[0].co + e.verts[1].co)/2
                        e.verts[1].co += (e.verts[1].co-center).normalized()*grow
                        e.verts[0].co += (e.verts[0].co-center).normalized()*grow

        self.payload = _pl

class SurfaceSmooth_OP(Master_OP):
    def generate(self):
        self.props['border'] = bpy.props.BoolProperty(name="Exclude border", default=True)
        self.props['iter']   = bpy.props.IntProperty(name="Iterations", default=2, min=1, max=10)

        self.prefix = "surface_smooth"
        self.name = "OBJECT_OT_SurfaceSmooth"
        self.start_mode = 'EDIT'

        def _pl(self, mesh, context):
            with abm.Bmesh_from_edit(mesh) as bm:
                limit_verts = set([])
                if self.border:
                    for e in bm.edges:
                        if len(e.link_faces) < 2:
                            limit_verts.add(e.verts[0].index)
                            limit_verts.add(e.verts[1].index)

                for _ in range(self.iter):
                    for v in bm.verts:
                        if v.index in limit_verts:
                            continue

                        ring1 = abm.vert_vert(v)
                        projected = []
                        for rv in ring1:
                            nv = rv.co - v.co
                            dist = nv.dot(v.normal)
                            projected.append(rv.co-dist*v.normal)

                        new_loc = mu.Vector([0.0, 0.0, 0.0])
                        for p in projected:
                            new_loc += p
                        new_loc /= len(projected)

                        v.co = new_loc

        self.payload = _pl

class EdgeSmooth_OP(Master_OP):
    def generate(self):
        self.props['border'] = bpy.props.BoolProperty(name="Exclude border", default=True)
        self.props['iter']   = bpy.props.IntProperty(name="Iterations", default=2, min=1, max=10)
        self.props['thres']  = bpy.props.FloatProperty(name="Threshold", default=0.95, min=0.0, max=1.0)

        self.prefix = "edge_smooth"
        self.name = "OBJECT_OT_EdgeSmooth"
        self.start_mode = 'EDIT'

        def _pl(self, mesh, context):
            with abm.Bmesh_from_edit(mesh) as bm:
                limit_verts = set([])
                if self.border:
                    for e in bm.edges:
                        if len(e.link_faces) < 2:
                            limit_verts.add(e.verts[0].index)
                            limit_verts.add(e.verts[1].index)

                # record initial normal field
                normals = []
                for v in bm.verts:
                    normals.append(v.normal)

                thr = self.thres

                for _ in range(self.iter):
                    # project surrounding verts to normal plane and move <v> to center
                    new_verts = []
                    for v in bm.verts:
                        new_verts.append(v.co)
                        if v.index in limit_verts:
                            continue

                        v_norm = normals[v.index]
                        ring1 = abm.vert_vert(v)

                        # get projected points on plane defined by v_norm
                        projected = []
                        n_diff = []
                        for rv in ring1:
                            nv = rv.co-v.co
                            dist = nv.dot(v_norm)
                            projected.append(rv.co-dist*v_norm)
                            n_diff.append(rv.co-projected[-1])
                            
                        # get approximate co-planar verts
                        coplanar = []
                        discord = []
                        for i, rv in enumerate(ring1):
                            r_norm = normals[rv.index]
                            if r_norm.dot(v_norm) > thr:
                                coplanar.append((i,rv))
                            else:
                                discord.append((i,rv))

                        for i, rv in discord:
                            # project 2-plane intersection instead of location
                            # which direction is the point? (on the v.normal plane)
                            # make it a 1.0 length vector
                            p = projected[i]
                            p = (p-v.co).normalized()

                            # v + n*p = <the normal plane of rv>, find n
                            d = r_norm.dot(p)
                            # if abs(d) > 1e-6:
                            if d > 1e-6:
                                w = v.co - rv.co
                                fac = r_norm.dot(w)/d
                                u = p * fac

                                # sanity limit for movement length
                                # this doesn't actually prevent the explosion
                                # just makes it a little more pleasing to look at 
                                dist = v.co-rv.co
                                if u.length > dist.length:
                                    u = u*dist.length/u.length
                                
                                projected[i] = v.co + u
                                #projected = [v.co + u]
                                break
                            else:
                                projected[i] = v.co

                        final_norm = v_norm
                        for i, rv in coplanar:
                            final_norm += r_norm

                        normals[v.index] = final_norm.normalized()

                        if len(projected) > 0:
                            new_loc = mu.Vector([0.0, 0.0, 0.0])
                            for p in projected:
                                new_loc += p
                            new_verts[-1] = new_loc / len(projected)

                        # move towards average valid 1-ring plane
                        # TODO: this should project to new normal (from coplanar norms), not old v.normal
                        # new_verts[-1] = v.co
                        # if len(coplanar) > 0:
                        #     total = mu.Vector([0.0, 0.0, 0.0])
                        #     for i, rv in coplanar: 
                        #         total += n_diff[i]
                        #     total /= len(coplanar)
                        #     new_verts[-1] += total                     

                            

                    # finally set new values for verts
                    for i, v in enumerate(bm.verts):
                        v.co = new_verts[i]

                bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

            #mesh.update(calc_edges=True)

        self.payload = _pl

class Mechanize_OP(Master_OP):
    def generate(self):
        self.props['border'] = bpy.props.BoolProperty(name="Exclude border", default=True)
        self.props['iter']   = bpy.props.IntProperty(name="Iterations", default=2, min=1, max=50)

        self.prefix = "mechanize"
        self.name = "OBJECT_OT_Mechanize"
        self.start_mode = 'EDIT'

        def _pl(self, mesh, context):
            with abm.Bmesh_from_edit(mesh) as bm:
                limit_verts = set([])
                if self.border:
                    for e in bm.edges:
                        if len(e.link_faces) < 2:
                            limit_verts.add(e.verts[0].index)
                            limit_verts.add(e.verts[1].index)

                ok_verts = []
                for v in bm.verts:
                    if v.index not in limit_verts:
                        ok_verts.append(v)

                ring1s = []
                for v in bm.verts:
                    ring1s.append(abm.vert_vert(v))

                for xx in range(self.iter):
                    print("iteration:", xx+1)
                    for v in ok_verts:
                        ring1 = ring1s[v.index]
                        projected = []
                        distances = []
                        for rv in ring1:
                            nv = rv.co - v.co
                            dist = nv.dot(v.normal)
                            distances.append(abs(dist)/nv.length)
                            projected.append(rv.co-dist*v.normal)

                        # dist_min = min(distances)
                        # for i in range(len(distances)):
                        #     distances[i] += dist_min

                        dist_sum = sum(distances)
                        new_loc = mu.Vector([0.0, 0.0, 0.0])

                        if dist_sum/len(projected) > 0.02:
                            for i, p in enumerate(projected):
                                new_loc += p*distances[i]/dist_sum
                        else:
                            for i, p in enumerate(projected):
                                new_loc += p
                            new_loc /= len(projected)

                        v.co = new_loc

        self.payload = _pl

class CleanupThinFace_OP(Master_OP):
    def generate(self):
        self.props['threshold'] = bpy.props.FloatProperty(name="Threshold", default=0.95, min=0.0, max=1.0)
        self.props['repeat'] = bpy.props.IntProperty(name="Repeat", default=2, min=0, max=10)

        self.prefix = "cleanup_thin_faces"
        self.name = "OBJECT_OT_CleanupThinFace"
        self.start_mode = 'EDIT'

        
        def _pl(self, mesh, context):
            bm = bmesh.from_edit_mesh(mesh)
            thr = self.threshold

            for _ in range(self.repeat):
                bm.edges.ensure_lookup_table()
                bm.faces.ensure_lookup_table()

                collapse_these = []
                for f in bm.faces:
                    s = 0.0
                    for e in f.edges:
                        s += e.calc_length()
                    s=s/2*thr
                    for e in f.edges:
                        if e.calc_length() > s:
                            mval = 100000.0
                            sed = None
                            for e in f.edges:
                                cl = e.calc_length()
                                if cl<mval:
                                    mval=cl
                                    sed=e
                            collapse_these.append(sed)
                            break

                #cthese = [bm.faces[i].edges[j] for i, j in res]
                cthese = list(set(collapse_these))
                print(len(cthese), "collapsed edges")
                
                bmesh.ops.collapse(bm, edges=cthese)
                bmesh.ops.connect_verts_concave(bm, faces=bm.faces)
            
            bmesh.update_edit_mesh(mesh)
            mesh.update(calc_edges=True)

        self.payload = _pl

class Cleanup_OP(Master_OP):
    def generate(self):
        #self.props['trifaces'] = bpy.props.BoolProperty(name="Only trifaces", default=False)
        self.props['fillface'] = bpy.props.BoolProperty(name="Fill faces", default=True)
        self.prefix = "cleanup_triface"
        self.name = "OBJECT_OT_CleanupTriface"
        self.start_mode = 'EDIT'
        
        def _pl(self, mesh, context):
            with abm.Bmesh_from_edit(mesh) as bm:
                # deselect all
                for v in bm.verts:
                    v.select = False

                # some preprocessing
                #e_len = np.empty((len(bm.edges)), dtype=np.float32)
                #for e in bm.edges:
                #    e_len[e.index] = (e.verts[0].co - e.verts[1].co).length
                #print(np.min(e_len), np.mean(e_len))
                #bmesh.ops.dissolve_degenerate(bm) #, dist=np.min(e_len))

                # find nonmanifold edges
                nm_edges = np.zeros((len(bm.edges)), dtype=np.bool)
                c3_edges = np.zeros((len(bm.edges)), dtype=np.bool)
                for e in bm.edges:
                    facecount = len(e.link_faces)
                    if facecount < 2:
                        nm_edges[e.index] = True
                    elif facecount > 2:
                        c3_edges[e.index] = True

                # A

                # remove all faces, connected to 3+ connection edge, that have nonmanifold edges
                delete_this = []
                for f in bm.faces:
                    nm = False
                    c3 = False
                    for e in f.edges:
                        if nm_edges[e.index]:
                            nm = True
                        if c3_edges[e.index]:
                            c3 = True
                    if nm and c3:
                        delete_this.append(f)               

                bmesh.ops.delete(bm, geom=delete_this, context='FACES')

                #if self.trifaces == False:
                bm.edges.ensure_lookup_table()
                bm.verts.ensure_lookup_table()

                c3_edges = np.zeros((len(bm.edges)), dtype=np.bool)
                for e in bm.edges:
                    if len(e.link_faces) > 2:
                        c3_edges[e.index] = True

                # B

                # mark non manifold verts (3-face-edge)
                # delete verts, select edges around the deleted vertices
                nonm_verts = set([])
                nonm_edges_idx = np.nonzero(c3_edges)[0]
                nonm_edges = [bm.edges[e] for e in nonm_edges_idx]

                for e in nonm_edges:
                    e.select = True
                    nonm_verts.add(e.verts[0].index)
                    nonm_verts.add(e.verts[1].index)

                for v in nonm_verts:
                    for v in abm.vert_vert(bm.verts[v]):
                        v.select = True

                # enum {
                # DEL_VERTS = 1,
                # DEL_EDGES,
                # DEL_ONLYFACES,
                # DEL_EDGESFACES,
                # DEL_FACES,
                # DEL_ALL,
                # DEL_ONLYTAGGED
                # };

                delete_this = [bm.verts[v] for v in nonm_verts]
                bmesh.ops.delete(bm, geom=delete_this, context='VERTS')

                # delete loose edges
                bm.edges.ensure_lookup_table()
                loose_edges = []
                for e in bm.edges:
                    if len(e.link_faces) == 0:
                        loose_edges.append(e)
                bmesh.ops.delete(bm, geom=loose_edges, context='EDGES')

                bm.edges.ensure_lookup_table()
                bm.verts.ensure_lookup_table()

                for e in bm.edges:
                    if len(e.link_faces) > 1 or len(e.link_faces) == 0:
                        e.select = False

                # C

                # fill faces for each loop
                # triangulate
                if self.fillface:
                    all_faces = []
                    for _ in range(2):
                        bm.edges.ensure_lookup_table()
                        loops = abm.bmesh_get_boundary_edgeloops_from_selected(bm)
                        new_faces, leftover_loops = abm.bmesh_fill_from_loops(bm, loops)

                        all_faces.extend(new_faces)
                        abm.bmesh_deselect_all(bm)

                        for l in leftover_loops:
                            for e in l:
                                e.select = True

                        # TODO: loops with 4 edge connections (one vert) could be 
                        #       split into 2 verts which makes the loops simple

                        print(len(leftover_loops))
                        if len(leftover_loops) == 0:
                            break

                    for f in all_faces:
                        f.select = True

                    bmesh.ops.recalc_face_normals(bm, faces=all_faces)
                    res = bmesh.ops.triangulate(bm, faces=all_faces)
                    smooth_verts = []
                    for f in res['faces']:
                        for v in f.verts:
                            smooth_verts.append(v)
                    smooth_verts = list(set(smooth_verts))
                    print(len(smooth_verts), "smoothed verts")
                    bmesh.ops.smooth_vert(bm, verts=smooth_verts, factor=1.0, use_axis_x=True, use_axis_y=True, use_axis_z=True)

                    # cleanup faces with no other face connections
                    bm.faces.ensure_lookup_table()
                    delete_this = []
                    for f in bm.faces:
                        no_conn = True
                        for e in f.edges:
                            if e.is_manifold:
                                no_conn = False
                        if no_conn:
                            delete_this.append(f)     

                    print(len(delete_this), "faces deleted after triface cleanup")
                    bmesh.ops.delete(bm, geom=delete_this, context='FACES')


        self.payload = _pl

class MeshNoise_OP(Master_OP):
    def generate(self):
        self.props['amount'] = bpy.props.FloatProperty(name="Amount", default=1.0, min=-1000.0, max=1000.0)
        self.props['scale'] = bpy.props.FloatProperty(name="Scale", default=1.0, min=0.0, max=1000.0)
        self.props['noisetype']= bpy.props.EnumProperty(
            items = [('DISTANCE','Distance','','',0), 
                    ('CHEBYCHEV','Chebychev','','',1),
                    ('MANHATTAN','Manhattan','','',2),],
            name = "Type",
            default = 'CHEBYCHEV')
        self.props['noisef']= bpy.props.EnumProperty(
            items = [('21','F2-F1','','',0), 
                    ('1','F1','','',1),
                    ('2','F2','','',2),],
            name = "Feature",
            default = '21')

        self.prefix = "mesh_noise"
        self.name = "OBJECT_OT_MeshNoise"
        self.start_mode = 'EDIT'

        def _pl(self, mesh, context):
            with abm.Bmesh_from_edit(mesh) as bm:
                df = None
                if self.noisef == '21': df = lambda x: x[1]-x[0] 
                if self.noisef == '1': df = lambda x: x[0] 
                if self.noisef == '2': df = lambda x: x[1] 

                for v in bm.verts:
                    d, _ = mu.noise.voronoi(v.co * self.scale, distance_metric=self.noisetype, exponent=2.5) 
                    v.co += v.normal * df(d) * self.amount

        self.payload = _pl

class EdgesToCurve_OP(Master_OP):
    def generate(self):
        self.props['balance'] = bpy.props.FloatProperty(name="Balance", default=0.99, min=0.0, max=1.0)

        self.prefix = "optimal_edge_flip"
        self.name = "OBJECT_OT_EdgesToCurve"
        self.start_mode = 'EDIT'

        def _pl(self, mesh, context):
            with abm.Bmesh_from_edit(mesh) as bm:
                traversed = np.zeros((len(bm.edges)), dtype=np.bool)
                for e in bm.edges:
                    if traversed[e.index]:
                        continue 

                    f = e.link_faces
                    # only if edge has two faces connected
                    if len(f) == 2:
                        # mark all both faces edges as traversed
                        for n in range(2):
                            for i in f[n].edges:
                                traversed[i.index] = True

                        e_len = e.calc_length()

                        # whats the max number edge can be rotated on the 2-face plane
                        max_rots = min(len(f[0].edges)-2, len(f[1].edges)-2)

                        # initial fit (find lowest angle between edge vert normals)
                        # vs. edge length
                        v0 = e.verts[0]
                        v1 = e.verts[1]
                        best = e_len*((v0.normal.dot(v1.normal)+1)/2)*self.balance + \
                            (e_len/(v0.co-v1.co).length)*(1.0-self.balance)
                        rotations = 0

                        # select vert that from which you take the next step doesn't end
                        # on a vert on the edge <e> (for each face loop)
                        # so that we have the first rotated edge position

                        fvi = [0, 0] 
                        for n in range(2):
                            fvi[n] = [i for i, fv in enumerate(f[n].verts) if e.verts[0] == fv][0]
                            n_step = (fvi[n]+1) % len(f[n].verts)
                            if f[n].verts[n_step] == e.verts[1]:
                                fvi[n] = n_step

                        for r in range(max_rots):
                            fvi[0] = (fvi[0]+1) % len(f[0].verts)
                            fvi[1] = (fvi[1]+1) % len(f[1].verts)

                            v0 = f[0].verts[fvi[0]]
                            v1 = f[1].verts[fvi[1]]

                            if v0 == v1:
                                continue

                            new_calc = e_len*((v0.normal.dot(v1.normal)+1)/2)*self.balance + \
                                (e_len/(v0.co-v1.co).length)*(1.0-self.balance)

                            if new_calc > best:
                                best = new_calc
                                rotations = r+1

                        # flip edge to optimal location
                        te = e
                        for _ in range(rotations):
                            te = bmesh.utils.edge_rotate(te, True)
                            if te == None:
                                break




        self.payload = _pl

class SplitQuads_OP(Master_OP):
    def generate(self):
        self.props['thres'] = bpy.props.FloatProperty(name="Threshold", default=0.5, min=0.0, max=1.0)
        self.props['normals'] = bpy.props.BoolProperty(name="Use Normals", default=False)

        self.prefix = "split_quads"
        self.name = "OBJECT_OT_SplitQuads"
        self.start_mode = 'EDIT'

        def _pl(self, mesh, context):
            with abm.Bmesh_from_edit(mesh) as bm:
                for f in bm.faces:
                    # for all quads
                    if len(f.edges) == 4:
                        # quad:
                        #  0
                        # 3 1
                        #  2

                        v = [i for i in f.verts]

                        # get two possible cut configurations
                        # either cut v[0],v[2] or v[1],v[3]

                        if not self.normals:
                            # case: v[0],v[2]
                            vec10 = v[0].co - v[1].co
                            vec12 = v[2].co - v[1].co
                            # note: ccw cross product
                            crp102 = vec10.normalized().cross(vec12.normalized())

                            vec30 = v[0].co - v[3].co
                            vec32 = v[2].co - v[3].co
                            crp302 = vec32.normalized().cross(vec30.normalized())

                            case02 = crp102.dot(crp302)

                            # case: v[1],v[3]
                            vec01 = v[1].co - v[0].co
                            vec03 = v[3].co - v[0].co
                            crp013 = vec01.normalized().cross(vec03.normalized())

                            vec21 = v[1].co - v[2].co
                            vec23 = v[3].co - v[2].co
                            crp213 = vec21.normalized().cross(vec23.normalized())

                            case13 = crp013.dot(crp213)
                        else:
                            case02 = v[0].normal.dot(v[2].normal)
                            case13 = v[1].normal.dot(v[3].normal)

                        if abs(case02) < self.thres or abs(case13) < self.thres:
                            if abs(case02) > abs(case13):
                                bmesh.utils.face_split(f, v[0], v[2])
                            else:
                                bmesh.utils.face_split(f, v[1], v[3])


        self.payload = _pl

class RebuildQuads_OP(Master_OP):
    def generate(self):
        self.props['decimate'] = bpy.props.FloatProperty(name="Decimate", default=0.1, min=0.0, max=1.0)
        self.props['quadstep'] = bpy.props.FloatProperty(name="Quad Angle", default=4.0, min=0.0, max=4.0)
        self.props['smooth'] = bpy.props.BoolProperty(name="Smooth", default=True)

        self.prefix = "rebuild_quads"
        self.name = "OBJECT_OT_RebuildQuads"
        self.start_mode = 'OBJECT'

        def _pl(self, mesh, context):
            ob = context.object

            temp_object = ob.copy()
            temp_object.data = ob.data.copy()
            temp_object.animation_data_clear()

            m_decimate = ob.modifiers.new(name="Decimate", type='DECIMATE')
            m_decimate.ratio = self.decimate

            bpy.ops.object.modifier_apply(modifier=m_decimate.name)

            if self.smooth:
                bpy.ops.object.mesh_refine_toolbox_surface_smooth(border=True, iter=2)

            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.tris_convert_to_quads(face_threshold=self.quadstep, shape_threshold=self.quadstep)
            bpy.ops.object.mode_set(mode='OBJECT')

            m_subd = ob.modifiers.new(name="Subd", type='SUBSURF')
            m_swrp = ob.modifiers.new(name="Shrinkwrap", type='SHRINKWRAP')
            #m_swrp.wrap_method = 'PROJECT'
            #m_swrp.cull_face = 'FRONT'
            m_swrp.target = temp_object

            for mod in context.object.modifiers:
                bpy.ops.object.modifier_apply(modifier=mod.name)

            meshname = temp_object.data.name
            objs = bpy.data.objects
            objs.remove(objs[temp_object.name], do_unlink=True)
            meshes = bpy.data.meshes
            meshes.remove(meshes[meshname], do_unlink=True)

        self.payload = _pl

bl_info = {
    "name": "Mesh Refine Toolbox",
    "category": "Mesh",
    "description": "Various tools for mesh processing",
    "author": "ambi",
    "location": "3D view > Tools",
    "version": (1, 1, 2),
    "blender": (2, 80, 0)
}


pbuild = PanelBuilder("mesh_refine_toolbox", "mesh_refine_toolbox_panel", \
    [Mechanize_OP(), SurfaceSmooth_OP(), Masked_Smooth_OP(), MergeTiny_OP(), CleanupThinFace_OP(), 
     Cleanup_OP(), CropToLarge_OP(), EvenEdges_OP(), MeshNoise_OP(), EdgesToCurve_OP(),
     SplitQuads_OP(), RebuildQuads_OP()])
OBJECT_PT_ToolsAMB = pbuild.create_panel()

def register():
    pbuild.register_params()
    bpy.utils.register_class(OBJECT_PT_ToolsAMB)

def unregister():
    pbuild.unregister_params()
    bpy.utils.unregister_class(OBJECT_PT_ToolsAMB)
    

